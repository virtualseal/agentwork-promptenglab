# Current restaurant objective

Thursday **5 PM America/Los_Angeles**, random restaurant from **Want to go only**,
within **10 straight-line miles** of Nijiya Market in San Mateo, channel
**C0CCRQUR6G1**. This supersedes historical two-list/10AM/15-mile notes below.
`./run` defaults to `restaurant.config.json`; it blocks without the complete real
Want to go snapshot. `.locals.example.json` is synthetic preview only.
Pacific follows San Mateo daylight saving. Live Slack,approved cloud runtime,
protected broker installation and deployment authorization remain pending.
No deployment or production send occurs during local implementation.

# Thursday Restaurants

A local restaurant picker with a standard-library worker for two Google Maps saved lists:
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
records one choice per local Thursday in a separate preview database (the configured state path plus `.preview`); repeated runs
return the existing status. Use a separate state path for an independent demo.

Copy `.locals.example.json` to ignored `.locals.json`, then set your own normalized
list files for offline fixtures, or use the public import setup below. Preview needs no environment variables. Do not put API keys, tokens, or passwords in locals. The app does not
read provider credentials or browser cookies.

```
./run once --config .locals.json
./run watch --config .locals.json
```

Watch is foreground, checks every minute, and stops with Ctrl-C. It stops after three consecutive prerequisite failures, with bounded backoff. Live mode requires explicit reviewed configuration and the scoped broker settings below. No scheduled OS startup or Railway deployment is installed.
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

`app/sources.py` defines list and Slack ports; its default Slack adapter is disabled.
Public import contacts Google only. Live CLI requires `live_reviewed: true`, a
complete imported snapshot, the fixed schedule/radius/channel, and installed broker
connection settings. These gates remain disabled in supplied local configuration.
The `preview` action always uses preview mode and separate state, even with a live config.

`app/service.py` persists the choice and delivery key before attempting delivery.
It checks authoritative Slack lookup before every write. Confirmed sends and
preview records are separate. Lost acknowledgements and process restarts reconcile
by delivery key before another post; unknown lookup blocks. Transient delivery
attempts are ten minutes apart, capped at three per Thursday and persisted across
restarts. Rejections stop immediately. No authoritative lookup capability means
live delivery stays blocked; Slack itself is not assumed to guarantee idempotence.
Provider adapters must implement this contract, including uncertain-write lookup.

Remaining activation: finish a fresh complete public import, confirm anchor coordinates,
install the administrator-reviewed Slack broker, verify authoritative
message readback in a separately authorized task, then separately authorize Railway deployment
with durable storage. No merge or deployment is authorized by this project.

The uninstalled Slack broker package and its result-only app port are documented
in [admin/SLACK_INSTALL.md](admin/SLACK_INSTALL.md). Writes default to disabled;
local live configuration remains disabled. Admin installation, external connection checks,
and controller review remain required before a later authorized activation.


## Complete public Maps import

See [admin/MAPS_IMPORT.md](admin/MAPS_IMPORT.md) for exact setup, verification,
recovery and current blockers. The ignored `.locals.json` has the two authorized
share URLs, channel, `maps_snapshot: local-data/maps.json`, the existing optional
browser interpreter path and `live_reviewed: false`. No provider key is needed.

```sh
./run import-maps --config .locals.json
./run preview --config .locals.json --now 2026-10-29T10:00:00-07:00 --seed 1
```

`app/maps_import.py` fetches both public pages and their complete list preloads,
pinned to list IDs and names, with current provider totals matching item counts. Continuations,
missing coordinates and unavailable lists block. Only nearby entries need public
primary-category verification. Labels equal to `restaurant` or ending in
` restaurant` qualify; cafes, bakeries, shops and hotels do not qualify solely by
name or embedded venue advertising. Missing nearby categories and restaurant
addresses block; the public place page can supply an address missing from the list.
The complete combined output is one fsynced atomic replacement; failed imports
leave the previous snapshot intact. There is no partial-list or example fallback.
Reimport explicitly to refresh; the worker reads the saved snapshot and does not
refresh Google data during delivery. Restart the worker after replacing its snapshot.
Playwright is optional for the import helper only, never imported by the worker.
No actual saved-place data belongs in Git.


Personal Railway access now uses only the project-local railway.connection.json
and a separate protected personal-thursday-railway integration. The shared
workspace credential is not a fallback. The connection is read-only and pending
admin installation plus an explicit environment binding. See
[personal connection setup](admin/PERSONAL_RAILWAY.md). No merge/deployment enabled.

The live worker refreshes the authorized Want to go list when selecting a new
week. It keeps the reserved choice across retries/restarts; it never reselects
after an uncertain send. Preview uses the saved snapshot and cannot send Slack.
