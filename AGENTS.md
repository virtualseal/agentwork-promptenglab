# Thursday Restaurants

Read ../AGENTS.md. Development/native runtime is agentwork UID502 under
/Users/agentwork/apps. CLAUDE.md is a relative symlink to this file.

Build-first restaurant picker: combine the user's Want to Go and SF Bay Area
lists, deduplicate, choose uniformly among restaurants within15 straight-line
miles of Nijiya Market,1956 S El Camino Real,San Mateo. Schedule Thursday10:00
America/Los_Angeles. Do not invent restaurants or treat sample fixtures as the
user's data. No cuisine/history/open-hours feature is authorized.

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
