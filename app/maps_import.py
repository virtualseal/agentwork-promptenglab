"""Fail-closed public Maps list import. No account, cookies or paid API."""
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import socket
import signal
import sys
import subprocess
import tempfile
import threading
import time
from urllib.parse import urlsplit, urljoin, unquote
from urllib.request import Request, build_opener, HTTPRedirectHandler
from .domain import Blocked, coordinate, distance_miles, Place, eligible, normalized
from .sources import Snapshot
from .maps_categories import verify_place_url

LISTS = (
    ('Want to go', 'https://maps.app.goo.gl/2njkf3jQ9rFdv3oG9', '1DDp738lZ0v-veWG0Y0vgQk4kTDI', 1331),
    ('sf / bay area', 'https://maps.app.goo.gl/DvyTg6yC8pNxh4eC8', 'UMx-6I1ETz2XzYiX7JOIdQ', 223),
)
HOSTS = {'maps.app.goo.gl', 'www.google.com', 'maps.google.com', 'google.com'}
MAX_BYTES = 8 * 1024 * 1024


def public_url(url):
    p = urlsplit(url)
    if (p.scheme != 'https' or p.hostname not in HOSTS or p.username or p.password
            or p.port not in (None, 443) or p.fragment or any(c in url for c in '\r\n')):
        raise ValueError('Public Maps host required')
    if p.hostname != 'maps.app.goo.gl' and not p.path.startswith('/maps'):
        raise ValueError('Public Maps path required')
    return url


class Redirects(HTTPRedirectHandler):
    def __init__(self):
        super().__init__()
        self.count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.count += 1
        if self.count > 5:
            raise ValueError('Too many Maps redirects')
        return super().redirect_request(req, fp, code, msg, headers, public_url(newurl))


def _fetch_direct(url):
    """Each attempt has a 25-second absolute deadline, including trickled reads."""
    public_url(url)
    for attempt in range(3):
        try:
            deadline = time.monotonic() + 25
            # No environment proxy, cookie jar, Authorization, or user browser state.
            from urllib.request import ProxyHandler
            opener = build_opener(ProxyHandler({}), Redirects())
            with opener.open(Request(url, headers={'User-Agent': 'Mozilla/5.0',
                                                    'Accept-Language': 'en'}), timeout=5) as response:
                public_url(response.url)
                sock = response.fp.raw._sock
                def expire():
                    try: sock.shutdown(socket.SHUT_RDWR)
                    except OSError: pass
                timer = threading.Timer(max(0, deadline-time.monotonic()), expire)
                timer.daemon = True
                timer.start()
                try:
                    body = response.read(MAX_BYTES+1)
                    if response.length not in (None, 0):
                        raise ValueError('Incomplete Maps response')
                    if len(body) > MAX_BYTES or time.monotonic() >= deadline:
                        raise ValueError('Maps response exceeded bounds')
                    return body.decode('utf-8')
                finally:
                    timer.cancel()
        except (OSError, TimeoutError) as error:
            if attempt == 2:
                raise Blocked('Public Maps request unavailable after three attempts') from error
            time.sleep(attempt+1)
    raise Blocked('Public Maps unavailable')


def bounded_process(command, payload, timeout):
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        stdout, _ = process.communicate(payload, timeout=timeout)
        if process.returncode:
            raise ValueError('Public data helper failed')
        return stdout
    finally:
        # Kill the helper's whole process group, including any browser descendants.
        try: os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError: pass
        process.wait()


def fetch_public(url):
    public_url(url)
    try:
        # Parent deadline also bounds resolver stalls before a socket exists.
        text = bounded_process([sys.executable, '-B', '-m', 'app.maps_import', '--fetch', url], '', 90)
        if len(text.encode()) > MAX_BYTES:
            raise ValueError('Oversized public response')
        return text
    except (OSError, ValueError, subprocess.SubprocessError):
        raise Blocked('Public Maps request unavailable within bounded attempts') from None


class PreloadLinks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == 'link':
            href = dict(attrs).get('href', '')
            if 'entitylist/getlist' in href:
                self.links.append(html.unescape(href))


def preload_url(page):
    parser = PreloadLinks()
    parser.feed(page)
    links = set(parser.links)
    if len(links) != 1:
        raise ValueError('Expected exactly one public list preload')
    url = public_url(urljoin('https://www.google.com', links.pop()))
    if urlsplit(url).path != '/maps/preview/entitylist/getlist':
        raise ValueError('Unexpected list endpoint')
    decoded = unquote(url)
    if len(re.findall(r'!4i(?:500|10000)(?=!|$)', decoded)) != 1:
        raise ValueError('List size protocol changed')
    return re.sub(r'(?i)(!4i|%214i)(500|10000)(?=!|%21|$)', r'\g<1>10000', url)


def parse_list(text, spec):
    name, _, list_id, _historical_count = spec
    if text.startswith(")]}'"):
        text = text[4:].lstrip()
    try:
        root = json.loads(text)
        data = root[0]
        items = data[8]
        if (len(root) != 7 or len(data) != 21 or data[0][0] != list_id
                or data[4] != name or root[1] != '' or type(data[12]) is not int
                or data[12] < 0 or not isinstance(items, list) or len(items) != data[12]):
            raise ValueError('Maps identity/count/continuation drift')
        return items
    except (IndexError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError('Public list schema changed or unavailable') from error


def nearby_rows(items, settings):
    rows = []
    for entry in items:
        try:
            lat = coordinate(entry[1][5][2], 90)
            lon = coordinate(entry[1][5][3], 180)
            # Even distant entries need coordinates: otherwise eligibility is unknown.
            if distance_miles(settings.latitude, settings.longitude, lat, lon) > settings.radius_miles:
                continue
            name, address = entry[2], entry[1][4]
            if not isinstance(name, str) or not name.strip():
                raise ValueError('Missing nearby place name')
            ids = entry[1][6]
            if len(ids) != 2 or not all(isinstance(v, str) and re.fullmatch(r'-?\d+', v) for v in ids):
                raise ValueError('Nearby place lacks feature identity (deleted or dropped pin)')
            cid = str(int(ids[1]) % (1 << 64))
            rows.append(dict(id=cid, name=name, address=address, latitude=lat, longitude=lon,
                             maps_url='https://www.google.com/maps?cid='+cid))
        except (IndexError, TypeError, KeyError) as error:
            raise ValueError('Missing Maps entry location/identity') from error
    return rows


class BrowserCategories:
    """Run an installed Playwright interpreter in an isolated ephemeral context."""
    def __init__(self, python):
        # Python locates pyvenv.cfg relative to the invoked executable. Resolving
        # its symlink selects the base interpreter and loses installed packages.
        self.python = os.path.abspath(os.fspath(python))
        if not Path(self.python).is_file():
            raise Blocked('Category browser interpreter is not installed')

    def __call__(self, row):
        helper = Path(__file__).with_name('maps_categories.py')
        try:
            stdout = bounded_process([self.python, '-B', str(helper)], json.dumps(row), 50)
            if len(stdout) > 8192:
                raise ValueError('Oversized category evidence')
            evidence = json.loads(stdout)
            if (evidence.get('cid') != row['id'] or evidence.get('name') != row['name']
                    or evidence.get('status') != 'verified_public_category'):
                raise ValueError('Category identity mismatch')
            verify_place_url(evidence['final_url'], row['id'])
            category = evidence['category']
            if not isinstance(category, str) or not category.strip() or len(category) > 150:
                raise ValueError('Missing public category')
            return evidence
        except (subprocess.SubprocessError, ValueError, KeyError, OSError):
            raise Blocked('Public place category unavailable; import remains incomplete') from None


def restaurant(category):
    label = category.casefold().strip()
    return label == 'restaurant' or label.endswith(' restaurant')


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.'+path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, ensure_ascii=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def configured_specs(settings):
    names=[normalized(name) for name,reference in settings.lists]
    catalog={normalized(spec[0]):spec for spec in LISTS}
    if len(set(names))!=len(names) or any(name not in catalog for name in names):
        raise Blocked('Configured Maps list is not authorized')
    return tuple(catalog[name] for name in names)


def import_lists(settings, classify, output, fetch=fetch_public, specs=None):
    """Commit only after every requested authorized list/category finishes."""
    specs=configured_specs(settings) if specs is None else specs
    evidence, lists, categories = [], {}, {}
    for spec in specs:
        page = fetch(spec[1])
        url = preload_url(page)
        # Bind the public page's preload to the approved list before fetching it.
        if '!1s'+spec[2]+'!' not in unquote(url):
            raise ValueError('Public page points at a different list')
        items = parse_list(fetch(url), spec)
        rows = nearby_rows(items, settings)
        selected = []
        for row in rows:
            cid = row['id']
            if cid not in categories:
                categories[cid] = classify(row)
            item = categories[cid]
            if (item.get('cid') != cid
                    or item.get('status') != 'verified_public_category'
                    or not isinstance(item.get('category'), str) or not item['category'].strip()):
                raise ValueError('Unclassified nearby entry or category identity drift')
            verify_place_url(item['final_url'], cid)
            if restaurant(item['category']):
                row['name'] = item.get('place_name') or row['name']
                if not isinstance(row['address'], str) or not row['address'].strip():
                    row['address'] = item.get('address')
                row['category'] = 'restaurant'
                Place.parse(row, spec[0])
                selected.append(row)
        lists[spec[0]] = selected
        evidence.append(dict(name=spec[0], list_id=spec[2], expected=len(items), count=len(items),
                             continuation=False, nearby=len(rows), restaurants=len(selected)))
    all_places = [Place.parse(row, name) for name, rows in lists.items() for row in rows]
    unique = eligible(all_places, settings)
    payload = dict(version=1, complete=True, captured_at=time.time(), lists=lists,
                   evidence=evidence, categories=categories, unique_restaurants=len(unique),
                   scope=dict(latitude=settings.latitude, longitude=settings.longitude,
                              radius_miles=settings.radius_miles))
    atomic_json(output, payload)
    return payload


class ImportedLists:
    def __init__(self, path, settings=None):
        path = Path(path)
        if path.stat().st_size > MAX_BYTES:
            raise Blocked('Imported snapshot exceeds bounds')
        self.data = json.loads(path.read_text())
        specs=configured_specs(settings) if settings is not None else tuple(s for s in LISTS if s[0] in self.data.get('lists',{}))
        if (not specs or self.data.get('version') != 1 or self.data.get('complete') is not True
                or set(self.data.get('lists', {})) != {s[0] for s in specs}):
            raise Blocked('Every configured public Maps list must be complete')
        if settings is not None:
            if self.data.get('scope') != dict(latitude=settings.latitude, longitude=settings.longitude,
                                               radius_miles=settings.radius_miles):
                raise Blocked('Imported snapshot radius/anchor differs from worker configuration')
        for spec, evidence in zip(specs, self.data.get('evidence', [])):
            if any(evidence.get(k) != v for k, v in dict(name=spec[0], list_id=spec[2],
                       continuation=False).items()) or (
                        type(evidence.get('expected')) is not int
                        or evidence['expected'] < 0
                        or type(evidence.get('count')) is not int
                        or evidence['count'] != evidence['expected']):
                raise Blocked('Imported list evidence changed')
        if len(self.data.get('evidence', [])) != len(specs):
            raise Blocked('Missing list completeness evidence')
        evidence_by_name={item['name']:item for item in self.data['evidence']}
        for name, rows in self.data['lists'].items():
            evidence=evidence_by_name[name]
            if (any(type(evidence.get(k)) is not int for k in ('restaurants','nearby'))
                    or not 0<=evidence['restaurants']<=evidence['nearby']<=evidence['count']
                    or not isinstance(rows,list) or len(rows)!=evidence['restaurants']):
                raise Blocked('Imported restaurant collection is incomplete or inconsistent')
            if not isinstance(rows, list):
                raise Blocked('Invalid imported place collection')
            for row in rows:
                category = self.data.get('categories', {}).get(row.get('id'), {})
                if (category.get('cid') != row.get('id') or (category.get('place_name') or category.get('name')) != row.get('name')
                        or category.get('status') != 'verified_public_category'
                        or not isinstance(category.get('category'), str)
                        or not restaurant(category['category']) or row.get('category') != 'restaurant'):
                    raise Blocked('Imported restaurant category evidence is missing')
                verify_place_url(category['final_url'], row['id'])
                Place.parse(row, name)

    def fetch(self, name, reference):
        name=next((key for key in self.data['lists'] if normalized(key)==normalized(name)),name)
        if name not in self.data['lists']:
            raise Blocked('Imported list not available')
        return Snapshot(tuple(Place.parse(row, name) for row in self.data['lists'][name]))


if __name__ == '__main__':
    if os.getuid() != 502:
        raise SystemExit('Thursday Restaurants requires agentwork UID 502')
    if len(sys.argv) != 3 or sys.argv[1] != '--fetch':
        raise SystemExit('Use ./run import-maps')
    try:
        sys.stdout.write(_fetch_direct(sys.argv[2]))
    except Exception:
        raise SystemExit('Public Maps fetch failed') from None
