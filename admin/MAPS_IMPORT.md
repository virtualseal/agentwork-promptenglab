# Public Maps import: human/controller handoff

Run as agentwork UID502 from /Users/agentwork/apps/thursday-restaurants.
No credentials, account sign-in, private profile, paid API, privileged install,
Slack post or Railway operation is part of this procedure.

## Ownership and prerequisites

app/maps_import.py owns bounded public HTTP, strict undocumented-format parsing,
nearby filtering, category orchestration and atomic combined snapshot storage.
app/maps_categories.py owns fresh isolated public browser primary-place metadata.
app/cli.py owns import locking, preview isolation and reviewed Slack wiring.
No new environment variable is introduced by import. Non-secret config fields:
`maps_snapshot`, `category_python`, `live_reviewed`; source `share_url` values
are recorded for humans, while code pins the two authorized URLs/identities.

The worker is standard-library only. Category import uses the already installed
Playwright 1.60.0 interpreter at
/Users/agentwork/apps/linkedin-agent/.venv/bin/python and its headless Chromium
revision 1223 cache. The helper creates a new in-memory browser context and never
loads a persistent user profile. Do not use ordinary Chrome or install another
browser to bypass an access restriction. An admin must provide an equivalent
reviewed browser environment if this existing environment becomes unavailable;
`category_python` is an explicit interpreter path, never a shell command. The
configured path is made absolute without resolving symlinks: virtualenv Python
must retain its lexical path to discover pyvenv.cfg and installed Playwright.

## Commands and results

Ignored .locals.json has both authorized share URLs, channel C0CCRQUR6G1,
Thursday10:00 America/Los_Angeles, radius15 and original Nijiya anchor. It is
preview mode with live_reviewed false. It has no example-file references.

```sh
id -un
id -u
pwd
./run import-maps --config .locals.json
./run preview --config .locals.json --now 2026-10-29T10:00:00-07:00 --seed 1
```

Success prints both source counts and the unique restaurant count. Import must
verify Want to go / 1DDp738lZ0v-veWG0Y0vgQk4kTDI and sf / bay area /
UMx-6I1ETz2XzYiX7JOIdQ, empty continuation, provider-reported total equal to
actual item count, and valid coordinates for every entry. Complete normal list
updates are accepted; historical counts1331/223 are research evidence only. The current research has 28+31 nearby entries,
51 unique CIDs before category filtering. These are research counts, not a fresh
import pass or the number of eligible restaurants.

HTTP accepts only public Google Maps HTTPS hosts, validates every redirect,
limits redirects to five, bodies to8MiB, socket waits to five seconds and each
response to25 seconds. Three safe read attempts are enclosed in a90-second
helper-process deadline, including DNS. Category subprocesses have50-second
limits and their whole process groups are cleaned up. Browser requests use only
Google metadata/static hosts and block images/media/fonts. Browser metadata is
bound to the original CID and primary heading/category, not a nested restaurant.
The helper samples heading/category/address/URL together in one DOM evaluation.
It requires three identical valid metadata samples at 200ms intervals within
12 seconds. Single loading placeholders (case-insensitive `Loading`, including
trailing whitespace, dots or an ellipsis), missing, empty, duplicate or changing
headings and execution-context
replacement reset stabilization; persistent failure aborts the import. Every
sample and final acceptance check the HTTPS Maps URL and exact single requested
CID; foreign redirects or CID changes abort immediately. The result-only client,
import and loaded restaurant evidence recheck the final URL/CID.
Missing restaurant addresses may be enriched from that page; missing coordinates,
feature IDs, categories or unresolved addresses fail closed. No name guessing.

One ignored local-data/maps.json contains both lists, category evidence, exact
counts, scope and capture time. It replaces the prior file only after all work
succeeds, using a same-directory temporary file, fsync and atomic rename.
The import lock serializes writers. Snapshot metadata is local evidence, not a
cryptographic attestation. Do not manually edit it. Back it up as private local
data before refresh if rollback is needed. On failure keep the last complete
snapshot, resolve the public access/schema issue and rerun the same command.
Never substitute example fixtures. Worker loads one snapshot at startup: stop
and restart it to adopt a completed refresh, retaining the same delivery database.
Do not restore an old delivery database to reroll a choice or retry a post.

## Controller validation and activation gates

The builder has not executed tests or independent review. Controller commands:

```sh
/usr/bin/python3 -B -m unittest discover -s tests -v
/usr/bin/python3 -B -m unittest discover -s evals -v
/usr/bin/python3 -B -m unittest discover -s tests -p test_maps_import.py -v
```

Synthetic tests cover completeness drift, partial failure preservation, identity,
category/address/location failures, dedup, nonrestaurants, foreign redirects,
retry limits, safe preview and bounded watch failures. They never contact Google.
Run the existing Slack/deployment focused checks from AGENTS.md as well.
admin/maps-package.json pins source bytes; refreshed Slack/Railway manifests
remain uninstalled and pending controller review.

Current cycle status (2026-10-28): local implementation and builder inspection
of the complete candidate relative to base 96c5549 are finished; controller tests
and fresh independent review on final bytes are pending. No suites or network
requests were run by this builder in this cycle. After controller checks/review,
a locally reviewed import implementation still does not establish a completed
live import or authorize activation.

Review-feedback repair: the carried implementation accepted a lone `Loading`
heading with populated controls after three samples. Loading placeholders now
reset the stability streak. Deterministic regressions cover persistent loading,
loading followed by valid metadata, and loading interrupting a valid streak.
These final bytes supersede earlier recorded suite results and require the
controller commands above plus a fresh independent review of the full candidate.

Historical ignored .review/maps-resume-attempt.json and maps-repair-attempt.json
record earlier public-request failures. Historical raw/category research is not
fresh validation or a runtime snapshot. This cycle neither refreshes that evidence
nor copies it to runtime output. Fresh public category/address behavior remains
unverified, including previously unresolved addresses. The heading race repair
has deterministic fixtures only; a future separately authorized network-enabled
agentwork UID502 session must run the import command above and inspect its
complete result locally. If access or provider format blocks that import, stop
and preserve the prior complete snapshot; do not weaken completeness/identity
gates or substitute research. No fresh network operation is authorized here.

Even after import, do not enable live_reviewed or broker writes in this task.
A later authorized activation requires controller tests/review on exact bytes,
confirmed anchor coordinates, protected Slack installation and workspace binding,
verified cloud runtime/durable storage and existing service binding. Readiness
stays503. The Slack broker receives provider credentials separately; worker uses
only SLACK_BROKER_URL, SLACK_BROKER_CAPABILITY and SLACK_WORKSPACE_ID from the
approved administrator environment. Never put the capability in locals.

The controller-reported virtualenv regression failure compared macOS path aliases
literally. It now compares physical prefix paths, retaining the assertion that
virtualenv and base prefixes differ. A complete two-row list with reported total
two is tested against historical count one; a partial one-row response with
reported total two still fails. Snapshot evidence uses the current verified
total, with identity and empty continuation checks retained.

Task-owned candidate files (including carried changes): AGENTS.md, README.md,
admin/INSTALL.md, admin/SLACK_INSTALL.md, admin/MAPS_IMPORT.md,
admin/maps-package.json, admin/slack-package.json, admin/railway-package.json,
app/cli.py, app/domain.py, app/maps_import.py, app/maps_categories.py,
tests/test_maps_import.py, evals/test_acceptance.py. CLAUDE.md remains the relative
symlink to AGENTS.md. Slack/Railway adapter code and registered service are
untouched. No installs, scheduling, Git writes, messages or deployment occurred.
