"""Pure selection and message rules; no provider access."""
from dataclasses import dataclass, replace
import hashlib
import json
import math
import random
import re
from urllib.parse import urlsplit, quote
from zoneinfo import ZoneInfo


class Blocked(RuntimeError):
    pass


def coordinate(value, maximum):
    if isinstance(value, bool):
        raise ValueError('Boolean coordinates are invalid')
    number = float(value)
    if not math.isfinite(number) or abs(number) > maximum:
        raise ValueError('Coordinate is out of range')
    return number


def maps_url(value):
    if not isinstance(value, str) or any(c in value for c in '\r\n'):
        raise ValueError('Invalid Google Maps URL')
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or parsed.hostname not in
            {'google.com','www.google.com','maps.google.com','maps.app.goo.gl','goo.gl'} or
            parsed.username or parsed.password or parsed.port not in (None,443)):
        raise ValueError('A public HTTPS Google Maps URL is required')
    if parsed.hostname in {'google.com','www.google.com','goo.gl'} and not parsed.path.startswith('/maps'):
        raise ValueError('Not a Google Maps place link')
    return value


@dataclass(frozen=True)
class Place:
    identifier: str
    name: str
    address: str
    latitude: float
    longitude: float
    url: str
    sources: tuple

    @classmethod
    def parse(cls, data, source):
        if not isinstance(data,dict):
            raise ValueError('Each place must be an object')
        category = data.get('category')
        if not isinstance(category,str) or not category.strip():
            raise ValueError('Place category must be verified before selection')
        if category.casefold().strip() != 'restaurant':
            return None
        name,address = data.get('name'),data.get('address')
        if not all(isinstance(v,str) and v.strip() for v in (name,address)):
            raise ValueError('Restaurant name and address are required')
        identifier=data.get('id')
        if identifier is not None and (not isinstance(identifier,str) or not identifier.strip()):
            raise ValueError('Invalid place identifier')
        identifier=identifier or hashlib.sha256((name.casefold()+'\0'+address.casefold()).encode()).hexdigest()
        return cls(identifier,name.strip(),address.strip(),coordinate(data.get('latitude'),90),
                   coordinate(data.get('longitude'),180),maps_url(data.get('maps_url')),(source,))


def distance_miles(lat1,lon1,lat2,lon2):
    a,b,c,d=map(math.radians,(lat1,lon1,lat2,lon2))
    value=math.sin((c-a)/2)**2+math.cos(a)*math.cos(c)*math.sin((d-b)/2)**2
    return 3958.7613 * 2 * math.asin(math.sqrt(min(1,max(0,value))))


def normalized(value):
    return ' '.join(re.sub(r'[^\w\s]',' ',value.casefold()).split())


def eligible(places, settings):
    # Build identity components before selection; a bridging record joins both
    # prior groups, regardless of source ordering.
    places=list(places)
    parents=list(range(len(places)))
    def find(index):
        while parents[index]!=index:
            parents[index]=parents[parents[index]]
            index=parents[index]
        return index
    by_id,by_location={},{}
    for index,place in enumerate(places):
        location=(normalized(place.name),normalized(place.address))
        for mapping,key in ((by_id,place.identifier),(by_location,location)):
            if key in mapping:
                parents[find(index)]=find(mapping[key])
            mapping[key]=index
    groups={}
    for index,place in enumerate(places):groups.setdefault(find(index),[]).append(place)
    unique=[]
    for group in groups.values():
        group.sort(key=lambda p:(p.identifier,p.name,p.address,p.latitude,p.longitude,p.url))
        canonical=group[0]
        if any(distance_miles(canonical.latitude,canonical.longitude,p.latitude,p.longitude)>0.05 for p in group):
            raise Blocked('Duplicate restaurant has conflicting coordinates')
        unique.append(replace(canonical,sources=tuple(sorted({source for p in group for source in p.sources}))))
    unique.sort(key=lambda p:(p.identifier,p.name,p.address))
    return [p for p in unique if distance_miles(settings.latitude,settings.longitude,p.latitude,p.longitude)<=settings.radius_miles+1e-9]


def choose(places,settings,rng=None):
    candidates=eligible(places,settings)
    if not candidates:
        raise Blocked('Neither list contains an eligible restaurant within the configured radius')
    return (rng or random.SystemRandom()).choice(candidates)


def slack_text(place):
    def escape(text):
        return text.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
    url=quote(place.url,safe=':/?&=,+%#@')
    return "Today we're going to eat here: "+escape(place.name)+'\n'+escape(place.address)+'\n<'+url+'|Open in Google Maps>'


@dataclass(frozen=True)
class Settings:
    mode: str
    timezone: str
    send_time: str
    radius_miles: float
    latitude: float
    longitude: float
    lists: tuple
    channel: str
    state_path: str
    anchor_name: str
    anchor_address: str

    @classmethod
    def load(cls,path):
        from pathlib import Path
        path=Path(path).resolve();data=json.loads(path.read_text())
        def reject_secrets(value):
            if isinstance(value,dict):
                for key,item in value.items():
                    if any(word in key.lower() for word in ('token','secret','api_key','password')):
                        raise ValueError('Use approved connection references, not credentials in local settings')
                    reject_secrets(item)
            elif isinstance(value,list):
                for item in value:reject_secrets(item)
        reject_secrets(data)
        if data.get('mode') not in ('preview','live') or data.get('weekday')!=3:
            raise ValueError('Choose preview/live mode and Thursday weekday3')
        zone=data['timezone'];ZoneInfo(zone)
        stamp=data['send_time']
        if not isinstance(stamp,str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',stamp):
            raise ValueError('send_time must be HH:MM')
        radius=data['radius_miles']
        if isinstance(radius,bool) or not isinstance(radius,(int,float)) or not math.isfinite(radius) or radius<=0:
            raise ValueError('Radius must be a finite positive number')
        lists=data.get('lists')
        if not isinstance(lists,list) or len(lists)!=2 or len({item['name'] for item in lists})!=2:
            raise ValueError('Configure both distinct source lists')
        refs=[]
        for item in lists:
            if not isinstance(item.get('name'),str) or not item['name'].strip():raise ValueError('List name required')
            filename=item.get('file')
            refs.append((item['name'],str((path.parent/filename).resolve()) if filename else None))
        channel=data.get('slack_channel')
        if data['mode']=='live' and (not isinstance(channel,str) or not channel.strip()):
            raise ValueError('Live delivery needs a Slack channel reference')
        anchor=data['anchor']
        return cls(data['mode'],zone,stamp,float(radius),coordinate(anchor['latitude'],90),
                   coordinate(anchor['longitude'],180),tuple(refs),channel or 'preview',
                   str((path.parent/data['state_path']).resolve()),anchor['name'],anchor['address'])

    def context(self):
        body={k:getattr(self,k) for k in ('mode','timezone','send_time','radius_miles','latitude','longitude','lists','channel')}
        return hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest()
