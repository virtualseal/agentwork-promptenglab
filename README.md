# Thursday Restaurants

A local, dependency-free restaurant picker for two Google Maps saved lists:
**Want to Go** and **SF Bay Area**. Every Thursday at **10 AM America/Los_Angeles**,
choose uniformly from the deduplicated restaurants within **15 straight-line miles**
of Nijiya Market, 1956 S El Camino Real, San Mateo. Pacific daylight saving changes
are handled by the timezone database. No Friday catch-up and no repeat-avoidance
rule are assumed.

The supermarket is an assumption about “Nigio”; correct its non-secret local
configuration if needed. Address reference: [Nijiya locations](https://www.nijiya.com/store-location).
Approximate anchor coordinates 37.54836, -122.31115 are from
[OpenStreetMap via Mapcarta](https://mapcarta.com/N305597766), pending confirmation.

## Try it locally

Run as agentwork UID502:

```
./run preview --now 2026-10-29T10:00:00-07:00 --seed 1
python3 -B -m unittest discover -s tests -v
```

Examples contain **fictional restaurants**, never your actual saved places. Preview
records one choice per local Thursday in `.state/preview.sqlite3`; repeated runs
return the existing status. Use a separate state path for an independent demo.

Copy `.locals.example.json` to ignored `.locals.json`, then set your own normalized
list files and, later, approved connection aliases. No environment variables are
required. Do not put API keys, tokens, or passwords in locals. The app does not
read provider credentials or browser cookies.

```
./run once --config .locals.json
./run watch --config .locals.json
```

Watch is foreground, checks every minute, and stops with Ctrl-C. It currently runs
**preview only**. No scheduled OS startup or Railway deployment is installed.
The launcher checks UID502 before starting. A state-file lock prevents overlapping
workers. Share one durable state path; separate databases cannot deduplicate each
other. Use one worker and persistent storage when eventually hosting it.

## List data contract

Each JSON file is an array, or `{ "complete": true, "places": [...] }`.
CSV supports the same columns. Required restaurant fields:

```
{"id":"stable-place-id", "name":"Restaurant", "address":"Street, City",
 "latitude":37.55, "longitude":-122.31, "category":"restaurant",
 "maps_url":"https://www.google.com/maps?q=Restaurant"}
```

Nonrestaurant categories are excluded; missing coordinates/categories block rather
than guessing. Both lists must load completely before selecting. Duplicate IDs or
normalized name/address pairs count once; conflicting coordinates block.

[Google documents sharing/exporting saved lists](https://support.google.com/maps/answer/7280933?co=GENIE.Platform%3DDesktop&hl=en).
Raw Takeout data can need verified category/location enrichment before satisfying
this normalized contract. There is no implemented private saved-list API adapter.
A generic Places API connection alone is not asserted to read your private lists.

## Delivery boundaries

`app/sources.py` defines future list and Slack ports; its default Slack adapter is
disabled. CLI refuses live mode until approved adapters are installed and reviewed.
Nothing in this release sends a Slack message or contacts Google/Railway.

`app/service.py` persists the choice and delivery key before attempting delivery.
It checks authoritative Slack lookup before every write. Confirmed sends and
preview records are separate. Lost acknowledgements and process restarts reconcile
by delivery key before another post; unknown lookup blocks. Transient delivery
attempts are ten minutes apart, capped at three per Thursday and persisted across
restarts. Rejections stop immediately. No authoritative lookup capability means
live delivery stays blocked; Slack itself is not assumed to guarantee idempotence.
Provider adapters must implement this contract, including uncertain-write lookup.

Remaining activation: supply both actual list sources, confirm supermarket/channel,
install administrator-reviewed scoped Google/Slack adapters, verify authoritative
message readback and live outcomes, then separately authorize Railway deployment
with durable storage. No merge or deployment is authorized by this project.

The uninstalled Slack broker package and its result-only app port are documented
in [admin/SLACK_INSTALL.md](admin/SLACK_INSTALL.md). Writes default to disabled;
the CLI still blocks live mode. Admin installation, external connection checks,
and controller review remain required before a later authorized activation.
