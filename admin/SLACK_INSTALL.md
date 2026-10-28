# Slack broker admin package (not installed)

This package is owned by Thursday Restaurants. Only `admin/slack_adapter.py`
may receive the Slack bot token; `app/broker_slack.py` implements the existing
`lookup(channel,key)` / `post(channel,text,key)` port using a separate scoped
HTTPS capability. No installed proxy operation is claimed or called. The
installed non-secret config inspected on 2026-10-27 has no Slack integration.
No chat Slack plugin is used. Railway deployment and Maps import remain separate
milestones. The existing CLI deliberately refuses live mode.

## Review and installation boundary

The controller must independently review the exact source and manifest before
an administrator installs anything. Nothing here authorizes service creation,
secret access, activation, deployment, or a Slack send in this task. A later
bounded task must verify installation and explicitly authorize activation.
The administrator chooses a separate protected broker identity/service and
binds its durable state volume. Never run that service with agentwork's files,
provider token, or the worker's environment. Agentwork UID 502 owns the app
worker, whose native/scheduled entry point remains `./run` with its early UID
check. No native startup job or cloud schedule has been installed.

The administrator must register a Slack bot in the intended workspace, record
its workspace ID and bot user ID, grant `chat:write` and `channels:history`, and
invite it to channel `C0CCRQUR6G1`. If the channel is private, use
`groups:history` instead of `channels:history`. Do not grant `chat:write.public`,
user tokens, or broad forwarding. Slack token scopes alone are not a per-channel
boundary: this broker enforces the fixed channel and a pinned workspace/bot
identity checked using `auth.test` before each operation. Review the bot's other
channel memberships and retention settings. Missing history access or metadata
visibility blocks delivery.

Reference contracts: [chat.postMessage](https://docs.slack.dev/reference/methods/chat.postMessage/)
and [conversations.history](https://docs.slack.dev/reference/methods/conversations.history/).
The history request sets `include_all_metadata=true`; every cursor must finish,
within 100 pages, 2 MiB, and a 25-second traversal budget. Rate limiting or these
bounds exhausting produces unknown, never absence. This can block a busy channel;
there is no unsafe fallback or automatic history-window narrowing.

## Package checks and exact entry points

From the reviewed package root, as agentwork UID 502:

```sh
id -un
id -u
pwd
/usr/bin/python3 -B -m unittest discover -s tests -v
/usr/bin/python3 -B -m unittest discover -s evals -v
/usr/bin/python3 -B -c 'import hashlib,json,pathlib; m=json.loads(pathlib.Path("admin/slack-package.json").read_text()); assert all(hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()==h for p,h in m["sha256"].items())'
```

The manifest pins the tested interpreter and source bytes. There are no
third-party packages. A cloud interpreter/OS combination needs its own reviewed
pin and validation in the Railway milestone; the macOS interpreter path is not
claimed portable. Do not update manifest hashes to bypass review.

On the separately protected administrator-managed broker service, set the
following environment variable NAMES through its approved secret/config
mechanism (never through app `.locals.json`, command arguments, logs, or chat):

* `SLACK_BOT_TOKEN`: provider credential, broker only.
* `SLACK_WORKSPACE_ID`, `SLACK_BOT_USER_ID`: verified identity bindings.
* `SLACK_BROKER_STATE`: absolute durable SQLite path, same volume as its `.lock`.
* `SLACK_CAPABILITY_SHA256`: SHA-256 of a fresh random scoped capability of at
  least 32 random bytes encoded as unpadded base64url. Only its digest belongs
  on the broker; give the capability itself only to this worker's scoped config.
* `SLACK_TLS_CERT`, `SLACK_TLS_KEY`: broker's certificate and protected key paths.
* `SLACK_BROKER_PORT`: optional port, default `8443`.

Use an administrator-owned directory and restrictive umask (`077`) for the
broker and state; agentwork must not be able to read its environment, token,
TLS key, state, or modify broker code. Backups must preserve both database and
filesystem ownership. Keep one broker process with persistent SQLite storage.
Expose only TLS with a trusted certificate matching the worker endpoint. The
source uses a direct TLS listener and does not trust forwarded identity headers.
Configure firewall, ingress request/time limits, service restarts, TLS renewal,
and secret injection through the admin's reviewed service manager. Those
external bindings do not exist yet and must be verified before activation.

Exact inactive entry point after those admin prerequisites are installed:

```sh
umask 077
python3 -B -m admin.slack_adapter
```

Writes are disabled by default. No request parameter can enable them. The only
write-enabled entry point, reserved for the subsequent authorized activation:

```sh
umask 077
python3 -B -m admin.slack_adapter --enable-writes
```

Stop the service and restart without `--enable-writes` to disable new posts.
Retain the same database and lock path. The HTTP protocol admits only POST
`/v1/slack`, bearer capability authentication, bounded JSON, version `1`, fixed
`channel`, `delivery_key`, and operation `lookup` or `deliver` (`text` only for
`deliver`). It never returns a provider response/token or accepts a Slack method,
URL, token, workspace override, or arbitrary provider parameters. Native Unix
socket support has not been installed or invented.

Future worker wiring constructs `BrokerSlack(endpoint, capability, workspace)`
and passes it to `app.service.run` as its Slack port. Worker configuration names
reserved for that wiring are `SLACK_BROKER_URL`, `SLACK_BROKER_CAPABILITY`, and
`SLACK_WORKSPACE_ID`; they are not currently read by the CLI. The capability
is a scoped broker credential, never a Slack provider key. Do not put it in the
non-secret `.locals.json`. No activation command can yet bypass the live CLI
gate; Maps completeness and later deployment gates must finish first.

## Recovery

The broker locks the journal across lookup and post, commits intent before
network writes, binds each key to its text digest, and persists at most three
post attempts across restarts. Explicit rejection is terminal. Explicit rate
limits defer at least 600 seconds (up to 86400 based on Retry-After). The worker
also has its existing independent three-attempt budget and ten-minute backoff;
this may stop earlier than the broker budget, never later.

After lost acknowledgement, timeout, malformed acknowledgement, wrong identity,
or a crash after intent, restart with the SAME state volume. A complete history
scan finding exactly one matching bot/workspace/key metadata message reconciles
it. Missing, ambiguous, incomplete, rate-limited, truncated, or unavailable
history is unknown. Even complete empty history cannot authorize retry after an
uncertain intent: retention, deletion, and delayed visibility cannot prove that
no message was delivered. A crash before the actual network write may therefore
require manual intervention. This deliberately favors a blocked delivery over
a duplicate.

Do not clear state, change keys, replay requests under a new key, or edit an
uncertain row to retry. Disable writes, retain the database and worker state,
and have the administrator inspect authoritative Slack history/audit evidence.
If that evidence cannot establish a safe outcome, leave the week blocked and
report it; no automated reset operation is supplied. Never restore an older
journal after writes. For rollback, stop writes, back up the stopped database
and lock ownership, restore the previously reviewed code only with compatible
state, and restart disabled. Do not roll back durable delivery evidence.

Before any subsequent activation, verify trusted TLS, capability rejection,
identity/channel scope, bot invitation/scopes, full metadata visibility, volume
persistence, single worker/broker, disabled-write behavior, reviewed package
hashes, and completed Maps/deployment gates. Local mock checks do not prove any
of these external bindings or live delivery.

## Transport deadline repair

The listening socket stays plain until accept. Each accepted socket gets a
5-second TLS handshake timeout before handshaking; a stalled anonymous handshake
therefore cannot block subsequent clients indefinitely. Headers and body have a
5-second total input deadline, and a timer shuts down the accepted TLS socket
at 80 seconds including handshake, dispatch and response. Provider/journal
budgets remain enforced independently; a disconnected request must reconcile
its durable intent before any later delivery attempt.

The worker uses direct HTTPS without redirect following. Its connect socket
waits are bounded to 5 seconds; a 35-second monotonic deadline, measured before
connect, shuts down the connected socket during request/response processing,
including trickling headers or body. System DNS resolution remains subject to
OS resolver policy (the stdlib socket connect timeout does not bound DNS).
Response status must be 200 and JSON remains bounded to 4096 bytes. Transport
failures return sanitized uncertainty, never authoritative absence.

The added transport tests require the installed `openssl` executable to generate
an ephemeral localhost certificate/key inside a temporary test directory. No
TLS key is shipped in this package and no external network/provider is used.
The controller must rerun all registered checks and independently review the
updated manifest before installation; previous check results cover older bytes.
