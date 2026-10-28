# Railway deployment package — local source only

Thursday Restaurants owns `admin/railway_adapter.py` (protected broker operation),
`admin/prepare_railway.py` (offline additive patch), `admin/railway_control.py`
(human-admin binding), `tools/railway_deploy.py` (UID502 result-only client), and
`deployment/` (inactive worker packaging). No installation, provider request,
service creation, deployment, credential access or startup has occurred.
The controller owns suites, independent review, commits and publication.

The installed non-secret `railway_projects.py`, `proxy.py`, `config.json` and
`client.py` were inspected on 2026-10-27. Hashes in `railway-package.json` pin
that baseline. The existing `workspace-railway` entry is reused through the
human-installed patch; the provider keeps loading its existing credential in
the protected service. No credential value, new key file, new integration,
new UID grant, or secret environment variable is needed. Its existing broad
`project.ensure` operation is not called by this client or expanded by this
patch. UID502 is shared across apps; it is not per-app isolation.

Fixed target: project `2d6b15bd-cdab-4978-9518-2d44820cfc85`, repository
`virtualseal/agentwork-promptenglab`, workspace
`1fc03572-3e94-4c8b-bb59-42dbc26e0d28`. Service/environment IDs are absent from
registered configuration. An admin must select existing IDs from inspection;
this package cannot create services, attach sources, change variables, obtain
keys, delete anything, merge, or forward arbitrary GraphQL.

Contracts reviewed: Railway's [services API](https://docs.railway.com/integrations/api/manage-services)
documents `serviceInstanceDeployV2(commitSha:)`; [deployment API](https://docs.railway.com/integrations/api/manage-deployments)
documents deployment status and metadata reads; [project API](https://docs.railway.com/integrations/api/manage-projects)
documents service/environment inspection. This code requires complete connection
pageInfo, UUID identities, and deployment metadata `commitHash` and `repo`.
Those metadata fields and the connected source/configuration must be verified
read-only by the admin before activation. Missing/different schema fails closed;
no live schema compatibility is claimed. No variable query is present.

## Controller checks (not executed by the builder)

As agentwork UID502 in `/Users/agentwork/apps/thursday-restaurants`:

```sh
id -un
id -u
pwd
/usr/bin/python3 -B -m unittest discover -s tests -v
/usr/bin/python3 -B -m unittest discover -s evals -v
/usr/bin/python3 -B -m unittest discover -s tests -p test_deployment.py -v
mkdir -p .review
/usr/bin/python3 -B -m admin.prepare_railway .review/railway-stage
```

The stage command requires a new output directory and verifies every baseline
and package hash before writing it. It generates full replacement non-secret
files, unified code patch and output hashes. No installed file changes.
Controller review must cover generated config and patch too. Do not refresh
baseline hashes to bypass drift. Rebase/review against the new baseline instead.
The manifest records the available macOS interpreter, not a tested cloud image.

## Human installation in a later authorized task

These commands are for an already authorized **human administrator session**,
not agentwork. No sudo or service provisioning is performed by the builder.
Stop the existing credential proxy using its already installed service manager
before replacing files; obtain its exact installed job label from the admin's
service inventory. That label is not known here and no invented restart command
is supplied. The broker must be stopped for the entire backup/install/rollback.

Execute privileged Python only from a root-owned, non-writable-by-agentwork
copy of the independently reviewed package (including its `admin/` modules and
manifest). The admin must compare those bytes with the controller's review
receipt before execution. Do not execute privileged code from the mutable app
checkout. All ancestor directories of the binding and approval must be root
owned and not group/world writable. The installed admin directory must satisfy
that condition; otherwise installation is blocked pending admin remediation.

From that protected reviewed package directory, using the reviewed stage above:

```sh
umask 077
export RAILWAY_STAGE=/Users/agentwork/apps/thursday-restaurants/.review/railway-stage
export RAILWAY_BACKUP="/Library/Application Support/CredentialProxy/admin/thursday-railway-backup"
/usr/bin/python3 -B -m admin.railway_install install --stage "$RAILWAY_STAGE" --backup "$RAILWAY_BACKUP"
/usr/bin/python3 -B -m admin.railway_control initialize
```

`railway_install` checks root identity, the installed baseline and staged bytes
against the reviewed package, creates a new non-secret backup, and installs only
four files. It never reads a credential. Root-owned code/config remain readable
by apiproxy and unwritable by agentwork. Restart the existing service through its
admin-managed job only after installation review. Initialization leaves writes
disabled. Initial binding contains null service/environment, permitting only
fixed-project inspection. As agentwork:

```sh
/usr/bin/python3 -B -m tools.railway_deploy inspect
```

Then in the human administrator session, enter the **existing** IDs returned
by that inspection (these are non-secret; prompts deliberately have no defaults):

```sh
read -r 'RAILWAY_SERVICE?Existing worker service UUID: '
read -r 'RAILWAY_ENVIRONMENT?Existing environment UUID: '
/usr/bin/python3 -B -m admin.railway_control bind --service "$RAILWAY_SERVICE" --environment "$RAILWAY_ENVIRONMENT"
```

These prompts use the workstation's zsh. Binding always disables writes and
clears any approval. Inspect again as agentwork to verify project membership.
The admin must verify that service's source is the exact approved repository,
autodeploy is disabled, no staged config changes exist, and the volume/runtime
requirements below hold. The adapter does not modify source/config or triggers.

## Approval and activation are blocked now

Current Maps import and live Slack activation are incomplete. No approval may
be issued yet. Missing service binding, protected approval, cloud runtime pin,
controller checks and independent review are additional pending gates. A
successful process health probe or Railway SUCCESS is never a delivery pass.

In the later bounded activation task, the admin creates a root-owned JSON
approval file outside the worker's writable tree with exactly these fields:

* `sha`: reviewed, published immutable 40-character lowercase commit SHA.
* `expires`: Unix seconds, future and at most 24 hours ahead.
* `checks`: each of `unit`, `acceptance`, `slack-runtime`, `deployment`,
  `independent-review` set to `passed` only with evidence for that exact SHA.
* `gates`: each of `maps_complete`, `slack_installed`, `source_repo_verified`,
  `autodeploy_disabled`, `no_staged_changes`, `durable_volume`, `single_worker`,
  `uid502`, `pacific_schedule` set to boolean true only after independent verification.

The file is a privileged attestation, not a caller-supplied check result.
After all gates really pass, in the human administrator session:

```sh
read -r 'RAILWAY_APPROVAL?Absolute protected approval JSON path: '
/usr/bin/python3 -B -m admin.railway_control enable --approval "$RAILWAY_APPROVAL"
```

As UID502, with the same reviewed SHA, the subsequent authorized task may use:

```sh
read -r 'RAILWAY_SHA?Reviewed immutable commit SHA: '
/usr/bin/python3 -B -m tools.railway_deploy submit --sha "$RAILWAY_SHA"
/usr/bin/python3 -B -m tools.railway_deploy reconcile --sha "$RAILWAY_SHA"
```

There is no branch argument or blind retry. A committed SQLite intent precedes
mutation; a full baseline of up to 100 deployments is required. Larger history
fails closed. A timed-out write, invalid ack or partial GraphQL error remains
unknown. Reconcile matches exactly one new deployment with the pinned SHA/repo,
and matches acknowledged ID when available. Missing metadata, incomplete history,
wrong SHA, multiple matches or no match never prove absence and never authorize
another write. No intent reset operation exists. Repeated submits for an intent
only read back; a different revision waits until all prior intents have verified
terminal outcomes. Failed builds report FAILED and are not retried. Preserve the
journal and lock across restarts; do not delete state to clear unknown results.
Admin investigation of provider history is required if authoritative evidence
cannot resolve an intent. Writes can be disabled while reconciliation continues:

```sh
/usr/bin/python3 -B -m admin.railway_control disable
```

Disable prevents new submissions after the current request releases its journal
lock; it cannot cancel an already accepted provider write. Quiesce requests and
stop the broker for an immediate hard maintenance boundary.

## Worker and separate Slack broker packaging

`deployment/worker.railway.toml` is opt-in source, not an installed Railway
configuration. It runs `/usr/bin/python3 -B deployment/worker.py`, which checks
UID502 before starting exactly one `./run watch` child. Existing `./run` also
checks UID502. Keep one replica, no overlapping rolling workers, one durable
volume mounted at `/data/worker`, and put configured SQLite and lock paths there.
Do not use an ephemeral filesystem. Settings retain Thursday 10:00
`America/Los_Angeles`; the worker polls internally, so no cloud cron or UTC
conversion is installed. Do not attach any branch with automatic deployments.

Worker environment variable NAMES: `THURSDAY_CONFIG` (absolute non-secret config
path), `PORT` (health HTTP port). No Railway provider key or `SLACK_BOT_TOKEN`
belongs in the worker. Runtime must include system Python with zoneinfo and
Pacific tzdata, and support UID502 and durable SQLite/flock. The local macOS
Python path/version is not evidence of a Railway Linux runtime. Admin must pin
and validate the existing service's runtime before enabling writes; no container
or cloud service was created in this task.

`/healthz` reports only child-process liveness. `/readyz` deliberately returns
503 until Maps/Slack runtime activation is implemented and verified; Railway
healthcheck uses `/readyz`, so this package cannot accidentally pass deployment
readiness now. Neither endpoint claims delivery. The CLI still blocks live mode.
The supervisor reaps its child if PORT parsing or HTTP binding fails, escalating
from terminate to kill after ten seconds. It polls child termination between
bounded HTTP accept waits and exits nonzero on unexpected child exit, allowing
the configured ON_FAILURE restart policy to recover. Each accepted HTTP connection
has a two-second socket timeout and absolute shutdown deadline covering headers
and response writes, so stalled or trickled headers cannot indefinitely hide
child failure. The deadline uses no new environment variables. Deployment CLI commands
consume the installed transport through its validated final receipt before
printing the JSON response body. An incomplete transfer exits without a result;
for uncertain submit outcomes use the documented reconcile command, never
blindly retry a mutation.

The Slack credential broker remains separately protected and admin installed,
with a different durable volume and identity, never a worker child or shared
filesystem. Exact broker entry points and environment variable NAMES remain in
[SLACK_INSTALL.md](SLACK_INSTALL.md). Railway deploy credentials remain solely
in the existing workstation credential proxy; they are not cloud worker or Slack
broker variables. This task creates neither service.

## Backup and rollback

Disable writes, quiesce calls, and stop the existing broker via its known admin
service manager. Restore only if installed files still match this package:

```sh
/usr/bin/python3 -B -m admin.railway_install rollback --stage "$RAILWAY_STAGE" --backup "$RAILWAY_BACKUP"
```

The installer refuses drift and preserves the backup. Restart the existing
broker via its admin-managed job. Keep the deployment journal and disabled
binding for audit/reconciliation; never roll back durable intent with code.
This restores the original proxy/config/railway_projects bytes and removes only
the added adapter. It does not roll back a cloud deployment or alter a provider.

Interrupted installation (for example power loss between atomic file replacements)
requires the broker to remain stopped. The installer makes the complete backup
before the first replacement but cannot atomically swap multiple files. A human
must compare each non-secret file to the backup and reviewed stage and restore
the three original files from that backup before restarting; never start a mixed
version or regenerate the baseline to accept it. Standard rollback deliberately
refuses a mixed/drifted installation so it cannot overwrite unrelated changes.
The earlier Slack package's AGENTS.md hash is refreshed for this app-guide update;
that package and this addition still require controller review on final bytes.
