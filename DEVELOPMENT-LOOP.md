# Local development loop

This repository-local queue runs one explicitly scoped task at a time, in a new
`agent/devloop-ID` Git worktree. It never merges, pushes, opens a PR, deploys,
modifies production settings or calls application providers. The existing shared
controller and blocked task `a49b117875df49c6` are untouched. No service is installed.

The existing controller requires a clean registered baseline; it cannot safely
consume this checkout's unrelated pending changes. This small local runner reuses
Git isolation, existing repository unittest/eval commands, installed Codex sign-in,
and the shared independent-review output schema. It is not a new provider broker.

## Backlog and execution

Create a JSON task file with exactly these fields (no secrets):

```json
{
  "problem": "Concrete reproducible defect or actionable review finding",
  "acceptance": "Observable outcome, failure cases, and regression expectations",
  "scope": ["app/owning_module.py", "tests/test_regression.py"],
  "priority": 0
}
```

Priority 0 is a reproducible bug/failed check, 1 an actionable review finding,
and 2 an explicitly approved objective. The queue never invents work. Enqueueing
is an explicit approval of this bounded task. Only explicit app/tests/evals code
files are accepted; credential client, configuration, dependency, deployment and
workflow changes require manual work. Do not place private contact data in tasks.
Tasks use the current **committed HEAD**, not uncommitted checkout files.

The reviewed candidate lives in an isolated checkout. Run as agentwork UID 502
and explicitly select the original repository to reuse its `.venv` and durable state:

```sh
cd /Users/agentwork/apps/linkedin-agent/.review/devloop-work
./run-devloop --repo /Users/agentwork/apps/linkedin-agent enqueue /absolute/path/task.json
./run-devloop --repo /Users/agentwork/apps/linkedin-agent status
./run-devloop --repo /Users/agentwork/apps/linkedin-agent prove TASK_ID
```

`prove TASK_ID` runs one explicitly selected eligible task while preserving the
`PAUSE` marker. It never releases the unattended queue or selects another task.
`watch` is the persistent unattended mode. It stays alive on an empty queue,
checks for newly queued work every five seconds, and runs offline discovery at
most every 15 minutes for an unchanged committed baseline. `once` and `work`
retain their bounded single-pass/drain behavior. To activate, remove pause with
`./run-devloop --repo /Users/agentwork/apps/linkedin-agent resume`, then start
`./run-devloop --repo /Users/agentwork/apps/linkedin-agent watch`. To survive
terminal disconnection, use:

```sh
nohup ./run-devloop --repo /Users/agentwork/apps/linkedin-agent watch \
  > /Users/agentwork/apps/linkedin-agent/.review/devloop/watch.log 2>&1 &
```

The worker holds its exclusive lock while idle. It writes PID, phase and last
activity time into `.review/devloop/worker.json`; `status` prints that record
and tasks. This is last-observed state, not an operating-system liveness proof. No scheduled startup or LaunchAgent
is installed. UID checks apply to every launcher path. Existing `.venv` is reused.
Codex must be signed in separately; app credentials are never loaded. The runner
uses `/Users/agentwork/.codex/packages/app-server-daemon/current/bin/codex`
with its matching installed tool host. A real read-only shell diagnostic verified
this runtime; the separate Homebrew runtime timed out negotiating its tool host.
No quarantine attributes, user settings, approval policies or sandbox levels
were changed to restore command execution.

Limits are fixed before execution: three implementation/review cycles, six Codex
launches (one usage unit per launch), 900 seconds wall time per task including
restart downtime, 240 seconds per agent, 120 seconds per required check,
30 seconds per commit, 15 seconds per helper Git operation (bounded by remaining task time), and 8 MiB per subprocess log. Application-provider spending
allowance is **$0**: no live application checks are authorized. Codex consumes
existing account usage: six launches is a usage limit, **not a hard dollar cap**.
If a hard monetary budget is required, unattended model execution needs a
metered/capped backend; this runner cannot enforce one and must remain paused.
Do not treat a subscription or a request quota as a dollar spending ceiling.

The worker reserves a cycle and a session before launching, and persists its
absolute deadline. Exhaustion blocks a task without resetting its budget. Other
eligible tasks continue. Local deterministic Git errors block for inspection;
failed checks and review findings may receive up to three cycles. No acceptance
criteria or required checks are weakened between attempts.

## Evidence and recovery

States are `queued → implementing → verifying → reviewing → ready`, with
separate `failed` (eligible bounded retry) and `blocked` states. Tests and evals
must pass, source must remain stable, and commit hooks must preserve the verified
index tree, committed file set, bytes, modes and parent. The complete committed
task diff must stay within the approved scope. Ignored private files added by
hooks fail the gate even if the worktree snapshot excludes their directory. A
**fresh read-only Codex process** must review the exact candidate HEAD and
full task diff. The reviewer gets requirements, rules, the exact candidate/base commits and
explicit verification records with check arguments, zero exit status, log paths
and hashes. It receives no builder transcript, rationale, feedback or general
task-directory pointer; it is instructed not to read those artifacts.
Readiness binds commit, all worktree source/modes, project/shared instructions,
runner bytes and review schema. `status` recomputes readiness rather than trusting
a stored label. New edits revoke readiness. Local ready is not CI/merge approval.

Private durable state is `.review/devloop/queue.sqlite3` (tasks, budgets, evidence,
state events). Each `.review/devloop/ID/` contains logs, reports and worktree;
`.review` is already ignored. Protect/back up this directory as private local
state. It is not published. Never copy live `.sdr-state` into task worktrees.

A file lock permits one worker. The subprocess supervisor and children retain
that lock if the worker dies, preventing restart from overlapping orphan work;
the supervisor enforces timeout and kills the process group. After lock release,
restart marks interrupted work blocked. Inspect its worktree/logs before:

```sh
./run-devloop --repo /Users/agentwork/apps/linkedin-agent resume TASK_ID
./run-devloop --repo /Users/agentwork/apps/linkedin-agent watch
```

Resume preserves all budgets and history. It does not authorize external writes.
`./run-devloop --repo /Users/agentwork/apps/linkedin-agent pause` prevents the
next subprocess, discovery and further task starts. Persistent `watch` stays
alive in the paused state. `resume` clears pause. `stop` sets both pause and
a durable stop marker, causing the watcher to exit; resume clears both markers
for an explicitly requested restart. A running subprocess may continue until
its existing timeout (at most 240 seconds for an agent). Stop the foreground worker
with Ctrl-C; interrupted state is recovered on restart. For background execution,
send TERM to the recorded worker process; bounded child supervision remains in
force. Resume without an ID removes the pause marker.

Locks, snapshots and receipts coordinate trusted agents sharing UID 502; they
are not tamperproof security boundaries. Agents still run under the managed
sandbox and broker policy. Repository comments cannot authorize new operations.
Actual merge/deployment gates remain external. This loop has no such operations
and does not establish GitHub branch protection or cloud capability.

## Harness evaluations

`python3 -B -m unittest discover -s devloop_evals -v` exercises failed-check
blocking, edit invalidation, restart recovery, retry exhaustion, independent task
progress, exclusive worker claims, setup failure, durable deadline exhaustion,
post-check hook mutation, hooks staging ignored private files, reviewer input
separation, selected proof execution while paused, and scope boundaries. Existing `tests/test_devloop.py`
includes these expectations in the normal test suite. They live outside the
allowed implementation scope. Tests use disposable Git repositories and fake
agents; they do not prove actual model review quality or live integrations.


## Verified real task

Task `7f6f264438ff498c` reached local `ready` on its first cycle, with two
fresh Codex sessions. Commit `cc19f3a` fixes empty/non-text/whitespace-only proxy
responses incorrectly returning HTTP 200. The builder reproduced three failing
HTTP cases before the fix; six application tests and three offline acceptance
evals pass afterward. A separate read-only reviewer checked the exact commit,
verified log hashes, independently reproduced red/green behavior and returned
`pass` without findings. A fresh runner process recomputed `ready_now=true`.
The `PAUSE` marker remained present throughout. This is a real code-change task
using mocked provider responses, not live paid generation or downstream business
verification. Its worktree and evidence remain under `.review/devloop/ID/`.
The original exhausted task is retained unchanged as history; it was not reset.


## Bounded discovery

Discovery is deterministic and makes no Codex calls while idle. It examines only
committed source in isolated detached worktrees, never the original checkout’s
uncommitted files or private contact/browser state. It runs existing tests/evals
and fixed probes of the existing generation failure contract in two fresh Python
processes. External socket connections are denied before importing application
or test code. Only an identical observed failure in both reports can become a
task. Import/dependency errors, skipped checks, timeouts and ambiguous ownership
are recorded as blockers rather than invented product work. Reports are private
under `.review/devloop/discovery-ID/`; cadence, reservations, admitted findings
and blockers persist in the `discovery` SQLite table.

At most one new task is admitted per pass. Its scope is at most four explicit
application/test files. Existing assertions keep their requirements; fixed
contract probes cover unusable content and malformed model/usage metadata. This
is deliberately bounded coverage, not general feature planning or a promise to
find every bug. Every admitted task still requires the normal builder, required
checks and independent exact-commit review before readiness.

A stable reproducer key prevents requeueing the same finding across restarts or
after exhaustion. Interrupted reservations remain visible for manual inspection
rather than replenishing budgets. A matching reviewed pending candidate is
rechecked offline: only an explicitly executed-and-passed reproducer counts as
a fix; a deleted/renamed test or absent probe does not. Up to three matching
candidate branches are searched, including older candidates hidden by a newer
unrelated fix. Uncertainty after that budget blocks admission instead of
creating a possible duplicate. If a candidate fixes the defect, discovery records
`pending_candidate` instead of creating a duplicate fix. This does not merge the
candidate or restore stale readiness evidence. Changing harness inputs still
invalidates prior receipts, while historical evidence remains in task events.

Optional review inputs live in `.review/devloop/review-inbox/*.json`:

```json
{
  "commit": "EXACT_COMMITTED_BASE",
  "reproducer": "contract:invalid-generation-metadata",
  "scope": ["app/llm/claude.py", "tests/test_app.py"],
  "detail": "Concrete defect and expected existing-contract outcome"
}
```

An input is actionable only when its commit, scope and reproducer match an
actual twice-observed failure. It receives review priority without accepting
commands, requested features or broader authority from its text. Invalid input
is skipped. A finding without reproducible evidence remains outside automatic
admission. Existing tasks with review findings continue within their original
three cycles; discovery does not reset blocked/exhausted tasks.

Each scan pass retains the 900-second ceiling, 120-second subprocess checks and
8 MiB logs. Git failures back off for 15 minutes while the worker remains alive.
Per-task model/time/retry limits and zero application-provider allowance are
unchanged. There is no merge/deploy/publication operation. No boot service was
installed; after a machine restart, use resume and the launch command above.


Discovery uses one absolute 900-second deadline from the initial Git preflight
through admission. Helper Git calls receive only the remaining time; the prior
deadline context is restored on every exit. Each matching candidate consumes
one of the three inspection slots before filesystem/Git checks, including
missing or dirty candidates. Uncertainty blocks admission unless another
candidate explicitly passes the reproducer.

Reservation and queue insertion check expiry inside their database transactions.
Discovery obtains an exclusive SQLite lock without busy waits before checking
and writing; a reader/writer lock conflict therefore blocks the scan rather
than waiting at commit past expiry. Expiry rolls back uncommitted task/event
writes. The connection’s normal timeout is restored afterward. A previously
committed reservation remains fail-closed if later admission fails. Failed scans
back off 15 minutes from failure without resetting any task budget.

## Independent review and automatic GitHub publication

The writer still cannot publish. After checks pass, a fresh read-only reviewer
receives the exact commit/task diff plus the complete publication file selection.
The controller binds that real review outcome and hash-checked test logs to the
shared review tool's current source/Git snapshot, then seals its normal receipt.
Preparing/sealing snapshots runs in bounded subprocesses; it does not add model
sessions. Every upload uses `review_gate.require_payload` again, including after
rate-limit waiting, so stale/missing receipts block remote writes.

Publication is explicitly configured in the original ignored state directory:
`.review/devloop/publishing/config.json` with boolean `enabled`, owner `virtualseal`
and repository `agentwork-promptenglab`. The installed scoped credential broker
holds GitHub credentials; neither writer nor controller receives them. The
reviewed `dev-controller` broker client supplies policy/release preflight and
transfer integrity. No personal gh login, token files, SSH keys or direct GitHub
HTTP calls are used. The repository's configured creation default is public.

`watch` queues publication for current ready tasks, keeping their remaining
original 900-second deadline. It uses unique `agent/task-ID-COMMIT` review
branches; it does not write main, merge, deploy or open PRs. The publication
controller has only branch-read and branch-publish operations. Its jobs, exact
manifests, expected heads, chunk intents and acknowledgements persist under
`.review/devloop/publishing/jobs/`. Each job has at most three attempts; an
interrupted/failed transfer blocks with its intent retained rather than silently
retrying. Task/model budgets and history are not reset.

For previously completed reviewed source, the user can authorize a distinct
publication-only job: create a JSON file with `root` (an existing clean worktree),
`branch` (`agent/...`) and concrete `requirements`, then run `publish-queue FILE`
with the normal `--repo` prefix. The source must share the project's Git common
directory. It gets at most 900 seconds, three attempts and six review sessions.
A current shared receipt is reused; otherwise an explicitly authorized
publication-only job runs the existing independent review workflow with the
project's required checks. Automatic task publication never starts an extra
model session to repair a missing/stale receipt.

Uploads contain only explicitly selected tracked UTF-8 files and the canonical
CLAUDE.md symlink. Workflow files require separate administrator capability and
are excluded, as are local HANDOFF files; runtime state, environments, contact
stores and credentials are not uploaded. Broker chunks stay below40,000 content
bytes,80 files and the JSON envelope bound. The controller paces calls to roughly
five per minute, below the shared ten-operation broker limit. Other apps still
share that quota and can cause a blocked publication.

After each chunk and at completion, the controller verifies both remote head
and the Git tree hash of the reviewed files/modes. README is published first to
replace the new repository's initializer. A lost write response retains its
original payload; explicit recovery reads authoritative branch state before an
exact idempotent replay. Conflicts or unreadable outcomes remain blocked. Local
and broker-created remote commit IDs differ; the source commit is recorded in
messages/jobs and the remote tree must match exactly.

`status` includes publication jobs, URLs and blockers. No GitHub Actions workflow,
branch protection, cloud target or deployment is provisioned. Main initially
contains only the repository initializer; reviewed code is on the review branches.

Publication receipts must also prove the exact registered test/eval argv and
zero exits; a focused passing check cannot substitute for the required suite.
The controller offers current-ready publication before starting another queued
implementation, so later work cannot consume an earlier task's remaining export
deadline. No budget is extended to accommodate a delayed upload.

New review branches are pinned to the exact default head/tree observed when this
repository was created. The configured `base_remote` is copied into each job.
If main/default changes, publication blocks before creating a branch; it never
silently adopts new inherited files or workflows. The broker independently
checks the expected default head when creating the new ref, covering a race
after controller readback. There is no automatic pin update.
