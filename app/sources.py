"""List and Slack ports. Live connections must be installed/reviewed later."""
import csv
import json
from pathlib import Path
from dataclasses import dataclass
from .domain import Blocked,Place


@dataclass(frozen=True)
class Snapshot:
    places: tuple
    complete: bool = True


class FileLists:
    def fetch(self,name,reference):
        if not reference:
            raise Blocked('Google Maps list connection is not configured: '+name)
        path=Path(reference)
        if not path.is_file() or path.stat().st_size>2*1024*1024:
            raise Blocked('Source list missing or exceeds the bounded import size: '+name)
        try:
            if path.suffix.lower()=='.csv':
                with path.open(newline='') as source:
                    raw=list(csv.DictReader(source))
            else:
                raw=json.loads(path.read_text())
                if isinstance(raw,dict):
                    if raw.get('complete') is not True:raise ValueError('List response is incomplete')
                    raw=raw['places']
            if not isinstance(raw,list) or len(raw)>10000:raise ValueError('Invalid list contents')
            places=[]
            for row in raw:
                if not isinstance(row,dict):raise ValueError('Invalid place row')
                lower={k.lower().strip():v for k,v in row.items()}
                normalized=dict(lower,name=lower.get('name',lower.get('title')),
                                maps_url=lower.get('maps_url',lower.get('url')))
                place=Place.parse(normalized,name)
                if place:places.append(place)
            return Snapshot(tuple(places))
        except (ValueError,TypeError,KeyError,OSError) as error:
            raise Blocked('List needs valid restaurant/location metadata: '+name) from error


def collect(settings,source):
    places=[]
    for name,reference in settings.lists:
        try:
            snapshot=source.fetch(name,reference)
        except Blocked:raise
        except Exception as error:raise Blocked('Source list unavailable: '+name) from error
        if not isinstance(snapshot,Snapshot) or snapshot.complete is not True:
            raise Blocked('Both source lists must finish loading before selection')
        places.extend(snapshot.places)
    return tuple(places)


@dataclass(frozen=True)
class Lookup:
    state: str  # present / absent / unknown
    message_id: str = None


class TemporaryFailure(RuntimeError):pass
class UncertainDelivery(RuntimeError):pass
class RejectedDelivery(RuntimeError):pass


class DisabledSlack:
    def lookup(self,channel,key):
        raise Blocked('Slack connection is not installed; no live message was sent')
    def post(self,channel,text,key):
        raise Blocked('Slack connection is not installed; no live message was sent')
