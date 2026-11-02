"""Isolated optional browser helper, invoked by maps_import; never a login profile."""
import json
import re
import sys
import time
from urllib.parse import urlsplit, parse_qs


def category_from_primary(text):
    # Only the primary place header, before tabs. Never embedded nearby venues.
    header = text.split('Overview', 1)
    if len(header) != 2:
        raise ValueError('Primary place header unavailable')
    labels = [line.strip() for line in header[0].splitlines()]
    hotels = [line for line in labels if re.fullmatch(r'[1-5]-star hotel', line)]
    if len(hotels) != 1:
        raise ValueError('Primary hotel category unavailable')
    return hotels[0]


def verify_place_url(url, cid):
    if not isinstance(url, str) or any(c in url for c in '\r\n\t'):
        raise ValueError('Invalid place URL')
    p = urlsplit(url)
    if (p.scheme != 'https' or p.hostname != 'www.google.com'
            or p.port not in (None, 443) or p.username or p.password or p.fragment
            or not (p.path == '/maps' or p.path.startswith('/maps/'))):
        raise ValueError('Foreign place redirect')
    if parse_qs(p.query, keep_blank_values=True).get('cid') != [cid]:
        raise ValueError('Place identity redirect changed')


# One JS turn captures identity and primary metadata together. Locator count/text
# calls in separate turns can observe different loading states or different places.
PRIMARY_SNAPSHOT = """() => ({
    url: location.href,
    headings: Array.from(document.querySelectorAll('h1'), e => e.innerText.trim()),
    categories: Array.from(document.querySelectorAll('button.DkEaL'), e => e.innerText.trim()),
    addresses: Array.from(document.querySelectorAll('button[data-item-id="address"]'),
                          e => e.getAttribute('aria-label') || ''),
    body: document.body ? document.body.innerText : ''
})"""


def primary_metadata(page, cid):
    """Require three matching samples, within 12 seconds; never retry identity drift."""
    deadline = time.monotonic() + 12
    previous, consecutive = None, 0
    while time.monotonic() < deadline:
        # Check navigation even if DOM evaluation fails during replacement.
        verify_place_url(page.url, cid)
        try:
            sample = page.evaluate(PRIMARY_SNAPSHOT)
        except Exception:
            # A destroyed execution context during navigation is transient. The
            # next sample must still pass URL/CID checks and all stability gates.
            previous, consecutive = None, 0
        else:
            verify_place_url(sample['url'], cid)
            headings, categories = sample['headings'], sample['categories']
            candidate = None
            # Maps can retain populated category/address controls while its lone
            # primary heading is still a loading placeholder. Repetition alone
            # must not turn that placeholder into a verified place name.
            if (len(headings) == 1 and headings[0].strip()
                    and not re.fullmatch(r'loading[\s.\u2026]*', headings[0].strip(), re.IGNORECASE)
                    and len(categories) <= 1):
                try:
                    category = categories[0] if categories else category_from_primary(sample['body'])
                except ValueError:
                    category = ''
                addresses = sample['addresses']
                address = None
                if len(addresses) == 1 and addresses[0].startswith('Address: '):
                    address = addresses[0][len('Address: '):].strip() or None
                if category and len(category) <= 150 and len(addresses) <= 1:
                    candidate = (headings[0], category, address)
            if candidate is None:
                previous, consecutive = None, 0
            else:
                consecutive = consecutive + 1 if candidate == previous else 1
                previous = candidate
                if consecutive >= 3 and time.monotonic() < deadline:
                    verify_place_url(page.url, cid)
                    return dict(place_name=candidate[0], category=candidate[1],
                                address=candidate[2], final_url=sample['url'])
        time.sleep(min(.2, max(0, deadline - time.monotonic())))
    raise ValueError('Primary place metadata missing, ambiguous or unstable')


def main():
    from playwright.sync_api import sync_playwright
    row = json.loads(sys.stdin.read(8193))
    if not re.fullmatch(r'\d{1,20}', row['id']):
        raise ValueError('Invalid CID')
    url = 'https://www.google.com/maps?cid='+row['id']+'&hl=en'
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        context = browser.new_context(locale='en-US', service_workers='block')
        def route(request):
            host = urlsplit(request.request.url).hostname or ''
            allowed = (host in {'www.google.com', 'maps.google.com', 'google.com'}
                       or host.endswith('.gstatic.com') or host.endswith('.googleapis.com')
                       or host.endswith('.googleusercontent.com'))
            if allowed and request.request.resource_type not in {'image', 'media', 'font'}:
                request.continue_()
            else:
                request.abort()
        context.route('**/*', route)
        page = context.new_page()
        page.set_default_timeout(12000)
        page.goto(url, wait_until='domcontentloaded', timeout=20000)
        metadata = primary_metadata(page, row['id'])
        print(json.dumps(dict(cid=row['id'], name=row['name'], **metadata,
                              status='verified_public_category')))
        context.close()
        browser.close()


if __name__ == '__main__':
    try: main()
    except Exception:
        print('Public category verification failed', file=sys.stderr)
        sys.exit(1)
