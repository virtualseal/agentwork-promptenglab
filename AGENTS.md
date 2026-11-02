# Thursday Restaurants

Read ../AGENTS.md. Development/native runtime is agentwork UID502 under
/Users/agentwork/apps. CLAUDE.md is a relative symlink to this file.

Current user objective supersedes historical two-list/10AM/15-mile notes:
choose uniformly from restaurants in ONLY the user's Want to go Google Maps
list within10 straight-line miles of Nijiya Market,1956 S El Camino Real,
San Mateo (37.54836,-122.31115). Send Thursday17:00 America/Los_Angeles to
C0CCRQUR6G1. Pacific means local daylight-saving time; fixed UTC-8 remains
unconfirmed. restaurant.config.json is the actual non-secret runtime configuration;
.locals.example.json contains synthetic preview fixtures only. No fake data may
substitute for the user's list. No cuisine/history/open-hours feature is authorized.

Sources and Slack are adapter interfaces. File fixtures make local preview
work; no Google account, Slack, geocoding or Railway provider is connected.
No browser cookies or direct provider keys. .locals.json is ignored non-secret
configuration/connection references, never token values. Real connections need
approved scoped adapters; do not invent broker operations. Do not merge/deploy
or send live Slack messages during this build. No paid provider checks.

app/domain.py owns validation, radius, dedup and message formatting;
app/sources.py owns local import and adapter ports; app/store.py owns durable
weekly selection/delivery state; app/service.py owns scheduling/retries and
uncertain-write reconciliation; app/cli.py owns local commands. Missing data or
partial list loads must block, not fall back to made-up results. Persist choice
before sending. A timed-out/unknown Slack outcome requires authoritative lookup
before retrying. Preview delivery is never marked as a real send.

Use one worker and durable SQLite storage. ./run has an early UID502 guard;
all scheduled/native startup paths use it. No startup service/cloud schedule
is installed. tests use fake adapters and temporary stores; never live APIs.

Verification: python3 -B -m unittest discover -s tests -v
Acceptance: python3 -B -m unittest discover -s evals -v
Preview: ./run preview --config .locals.example.json --seed 1
No third-party runtime dependencies. Existing Railway service is untouched.

Slack milestone ownership: admin/slack_adapter.py owns the uninstalled protected
broker, fixed-channel Slack HTTPS calls, journal/locking and TLS capability
endpoint; app/broker_slack.py owns the result-only Slack port. Setup, installation
boundary, exact entry points, protocol, recovery and all environment variable
NAMES are in admin/SLACK_INSTALL.md. admin/slack-package.json pins reviewed
package bytes and the locally tested Python version; no third-party runtime
packages. tests/test_slack_runtime.py contains mocked runtime regressions.
The controller owns independent review, commits and publishing. Nothing is
installed/connected; CLI live mode remains blocked. Do not run the admin broker
as part of app startup or give the worker SLACK_BOT_TOKEN. No shared proxy files
are modified. Keep broker durable state separate from worker state.

Slack transport deadlines: admin/slack_adapter.py accepts raw sockets before
TLS, bounds handshakes to 5 seconds, request headers/body to 5 seconds and the
socket exchange to 80 seconds. app/broker_slack.py bounds connect socket waits
to 5 seconds and interrupts response headers/body at a 35-second deadline.
Transport regressions in tests/test_slack_runtime.py use loopback sockets and
an ephemeral synthetic TLS identity generated with the installed `openssl`
command (test-only prerequisite, no extra Python runtime dependency). No new
environment variables or installed services are introduced by this repair.
Controller owns execution of the documented suites and independent review.

Slack response completeness repair: both HTTPS clients reject premature EOF
when Content-Length bytes remain, before parsing even valid JSON. Chunked
termination errors also fail closed. Mocked HTTP-parser regressions cover
complete bodies, short declared-length bodies and missing final chunks;
incomplete history cannot authorize a post, and incomplete broker replies
remain unknown. Setup and environment variable names remain in
admin/SLACK_INSTALL.md; no new variables. Controller runs checks/review.

Railway milestone ownership: admin/railway_adapter.py owns fixed-target inspect,
immutable-SHA submit and read-only reconciliation; admin/prepare_railway.py owns
baseline-pinned additive installed proxy/schema/config patch generation;
admin/railway_install.py and railway_control.py are human-admin-only installation,
backup/rollback and disabled-by-default binding controls. tools/railway_deploy.py
is the UID502 result-only client. admin/INSTALL.md has exact commands, protected
approval format, pending external gates and recovery. admin/railway-package.json
pins non-secret baseline and package bytes; no credential values are read/copied.
Existing workspace-railway credential binding is reused only after human install.
No installed/shared code, credentials, Railway services or Git state are changed.

Deployment packaging: deployment/worker.py has an early UID502 guard and runs
one ./run watch child; deployment/worker.railway.toml is inactive source requiring
an existing validated runtime and durable /data/worker volume. Worker variable
NAMES: THURSDAY_CONFIG, PORT. Slack broker variables remain exclusively documented
in admin/SLACK_INSTALL.md; no Railway key is a worker variable. Health is process
liveness only; readiness stays 503 while Maps/Slack activation is incomplete.
Schedule remains Thursday10AM America/Los_Angeles with durable SQLite and flock.
No container, startup job or cloud schedule was created or launched.

Controller checks: /usr/bin/python3 -B -m unittest discover -s tests -v;
/usr/bin/python3 -B -m unittest discover -s evals -v; focused mocked regressions:
/usr/bin/python3 -B -m unittest discover -s tests -p test_deployment.py -v.
The deployment tests import only installed non-secret transport/journal helpers,
never instantiate providers or contact APIs. Builder does not execute suites or
independent review in this bounded task. Pending service/environment binding,
cloud runtime pin, complete Maps import, live Slack installation, exact-head
checks and independent review block activation. Full handoff: admin/INSTALL.md.

Railway review repair: tools/railway_deploy.py consumes the installed client's
stream through its validated final receipt before printing the JSON body; failed
or incomplete transfers produce no success output and are never retried here.
deployment/worker.py protects post-spawn startup with child cleanup, reaps on
invalid PORT/bind failure, and exits nonzero after unexpected child termination
so the existing ON_FAILURE policy can recover. tests/test_deployment.py owns
mocked CLI transfer and supervisor lifecycle regressions. No environment variable
names or setup boundaries changed; controller runs the checks above and reviews
final package bytes before installation or activation.

Supervisor request deadline repair: deployment/worker.py owns a two-second
absolute accepted-connection deadline and socket timeout, including incomplete
or trickled headers and response writes. tests/test_deployment.py adds a real
loopback stalled-header regression checking nonzero exit after child failure
and server closure. No setup or environment variable names changed. Controller
executes the documented checks and independent review; builder has not run them.

Maps import ownership: app/maps_import.py owns public list HTTP/parsing, strict
authorized identity/current-count/continuation gates, nearby filtering and atomic ignored
combined snapshot output. app/maps_categories.py owns isolated optional public
Playwright category/address enrichment, bound by CID; no login/profile/cookies.
app/cli.py owns import locking, snapshot-backed runtime, safe preview isolation,
reviewed BrokerSlack wiring and three consecutive watch-failure limit. Settings
names maps_snapshot, category_python, live_reviewed are non-secret. No Maps env
variables. Worker Slack variable NAMES now read behind live gates:
SLACK_BROKER_URL, SLACK_BROKER_CAPABILITY, SLACK_WORKSPACE_ID; provider tokens
remain forbidden. Preview always overrides live mode and uses separate state.

Setup/recovery/exact commands: admin/MAPS_IMPORT.md. Run ./run import-maps
--config .locals.json; ignored locals records both authorized share URLs/channel,
preview mode and live_reviewed false. Real output is ignored local-data/maps.json;
actual saved-place records never belong in fixtures/Git. Worker uses the imported
snapshot until restart; refresh is explicit. Category import reuses installed
Playwright1.60.0/headless Chromium1223 through the existing linkedin-agent venv;
worker runtime has no third-party dependency. No new browser/service is installed.
New synthetic regressions: tests/test_maps_import.py and final pipeline eval in
evals/test_acceptance.py. Controller owns all suite execution and independent
review: /usr/bin/python3 -B -m unittest discover -s tests -v;
/usr/bin/python3 -B -m unittest discover -s evals -v; focused Maps check:
/usr/bin/python3 -B -m unittest discover -s tests -p test_maps_import.py -v.
Builder has not executed suites/review. admin/maps-package.json pins local source;
Slack/Railway manifest hashes are refreshed, not approved or installed.
Fresh requests for both lists failed DNS; browser tool requires unavailable
approval. Ignored .review/maps-import-attempt.json and maps-parser-evidence.json
preserve the blocker and old raw counts1331/223, nearby28+31. Four nearby entries
lack list addresses; public page enrichment is still unverified. No completed
runtime import, Slack send, activation or deployment is claimed. Readiness stays
503 and all prior human installation/runtime/service-binding gates remain.

Maps helper interpreter repair: BrowserCategories preserves the configured
absolute lexical executable path, including virtualenv symlinks; resolving the
symlink loses pyvenv.cfg and Playwright. tests/test_maps_import.py includes a
real temporary symlinked virtualenv subprocess regression without network or
third-party packages. No new environment variables, launcher, or service.
Controller owns all test execution and independent review. Complete live import
remains pending public network access and verified category/address enrichment;
preserved research is not substituted into runtime output. See
admin/MAPS_IMPORT.md for the current blocker and recovery command.

Maps completeness repair: historical1331/223 counts are evidence only. The parser
requires a nonnegative integer provider total equal to actual items and empty
continuation; snapshot loading checks current recorded totals agree. Authorized
list IDs/names remain pinned. tests/test_maps_import.py covers complete growth,
partial growth rejection and inconsistent snapshot totals. Its venv regression
compares resolved prefix paths to account for macOS /var -> /private/var aliases,
while still proving the child retains a distinct virtualenv prefix. No setup or
environment variable changes. Controller owns all test execution and review.

Maps primary-heading race repair: app/maps_categories.py samples primary heading,
category, address and URL in one DOM evaluation, requiring three identical valid
samples at 200ms intervals within 12 seconds. Missing/ambiguous/loading headings
and transient execution-context failures reset stabilization; persistent failures
block. Every sample and accepted result retain the requested HTTPS Maps CID;
helper replies, import and loaded restaurant evidence also check the final CID.
No category from a different place is accepted. Deterministic DOM/clock regressions
in tests/test_maps_import.py cover transient/persistent headings, missing metadata,
foreign redirects/CID drift, dependency failure, retry and partial-result safety.
No new dependencies, environment variable names or startup paths. Setup/recovery
and exact controller commands remain in admin/MAPS_IMPORT.md. This cycle is local
source inspection/implementation only: builder has not run suites, independent
review or public requests. Controller must test and independently review the full
candidate relative to 96c5549 before a local commit. Live import/activation remain
separate pending gates; old ignored research is not fresh network validation.

Maps loading-placeholder feedback repair: primary_metadata rejects a lone
case-insensitive Loading heading with optional trailing whitespace/dots/ellipsis
before counting stable samples, even with populated category/address controls.
Deterministic regressions cover persistent loading, eventual valid metadata and
streak reset. Controller must rerun the documented tests/evals and obtain fresh
independent review on the complete candidate; builder ran no suites or network
requests. Ownership, setup and environment variable names above are unchanged.


Personal Railway connection supersedes the shared workspace credential plan:
railway.connection.json and tools/railway_deploy.py route only to
personal-thursday-railway. No credential values in the app. Environment remains
unbound until admin-selected and exact-binding review. admin/personal_railway.py
is fixed-query read-only project-token inspection; admin/prepare_personal_railway.py
stages an additive protected proxy patch,admin/install_personal_railway.py is
human-admin-only source. No provider/deployment mutations or credential fallback.
Legacy prepare_railway is disabled. admin/PERSONAL_RAILWAY.md owns exact setup,
protected token import,stop/restart boundaries and rollback. Existing Truewind
plugin remains separate. Tests/test_personal_railway.py uses no live providers.

For this personal project, do not use the globally connected Railway plugin or
global CLI sign-in (currently work/Truewind). Always use this project's bound
result-only client. Missing personal adapter/environment/credential is a blocker,
never authority to try the work connection. This instruction routes trusted
agents; it does not isolate hostile code running as the same UID.

Current goal implementation: app/maps_import.py imports only configured authorized
lists, validates exact configured snapshot membership/completeness/scope, and
app/cli.py defaults to restaurant.config.json. Legacy two-list fixture lives in
tests/fixtures/two-list-settings.json for generic regression coverage. No runtime
startup,Slack activation or Railway deploy has been installed by these edits.

Live selection uses app/cli.RefreshingLists to fetch/verify only the configured
Want to go list before reserving a new week. Retries/restarts preserve the durable
choice without refreshing/reselecting. Preview uses the explicit imported
snapshot and never instantiates Slack. Existing signing/TLS/runtime/activation
and no-deploy boundaries remain. New eval proves next-week list changes apply.

Personal discovery continuation: admin/personal_railway.py adds fixed read-only
bound-environment service metadata after token identity validation. No account-
wide access is claimed. admin/upgrade_personal_discovery.py is human-admin-only
source-only upgrade using the existing protected token (never copied/read here).
See admin/PERSONAL_DISCOVERY.md. Installed adapter remains old until admin acts.

Linux worker packaging: deployment/worker.Dockerfile pins the official amd64
Playwright1.60.0 browser image and matching Python package, with application
installation/execution as UID502. Its Dockerfile-specific ignore file and COPY
allowlist exclude credentials, admin adapters and real saved places. Cloud-only
paths are in deployment/worker.config.json; it remains preview/live_reviewed=false.
See deployment/LINUX_WORKER.md. Explicit local container verification command:
python3 -B deployment/verify_linux_worker.py --host unix:///Users/agentwork/.colima/restaurant-build/docker.sock
This requires the dedicated running project VM, uses an empty project Docker
client config and offline synthetic pages, verifies current source hashes and
SQLite state across two containers, then deletes only its temporary volume.
It is not a cloud storage, live Maps, Slack, ingress or delivery verification.
No Railway start paths/health gates were activated or changed. The original
market-briefing-scheduler remains untouched; do not copy its Slack credential
into the application worker. All prior no-merge/no-deploy boundaries remain.

Native Linux verification preparation: admin/ci/restaurant-linux-verify.yml is
an inactive, human-install-only manual-dispatch workflow template. It requires
a dedicated native x64 Linux agentworkUID502 runner under /Users/agentwork/apps
and a rootless engine, never a host-root Docker grant. No runner was registered.
deployment/native_linux_check.py owns exact-dispatched-SHA, UID/path/native-engine
gates and bounded offline build/browser/storage execution; its early UID guard
also applies to scheduled invocation. tests/test_native_linux_check.py covers
wrong identity, emulation, stale checkout and unsafe engine rejection. See
admin/ci/README.md for prerequisites and preserved no-merge/no-deploy boundaries.

2026-11-02 CI-only user exception supersedes the native-runner requirement above:
GitHub-hosted verification may use its standard LinuxX64 UID1001 runner and
workspace. deployment/verification_identity.py scopes this to hosted metadata,
exact repository/workspace and immutable GitHub SHA; local commands still require
agentworkUID502. Only build/check tools use the exception. The app image, ./run
and deployment/worker.py retain UID502. No production credentials, Slack calls,
merge or deployment are authorized. See admin/ci/README.md for exact human-only
workflow installation and Actions run instructions; the template stays inactive
until an administrator installs it through the supported workflow path.

The hosted workflow is installed only on the default branch and accepts an
explicit reviewed source_sha. Checkout and EXPECTED_COMMIT use that immutable
source SHA rather than the workflow's own commit; no duplicate workflow install
on the source branch is needed. Hosted event SHA remains recorded by GitHub.
