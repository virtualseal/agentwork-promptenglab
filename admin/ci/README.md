# Native restaurant verification — admin installation package

User authorization on2026-11-02 permits GitHub-hosted CI's standard identity and
workspace for VERIFICATION ONLY. The Mini remains agentworkUID502 under
/Users/agentwork/apps. Application installation and execution inside the worker
image remain UID502; the app launchers are unchanged. No production credential,
Slack send, merge or deployment is authorized. Maps still refreshes automatically;
no exports or frozen-list fallback are introduced.

The template restaurant-linux-verify.yml is not installed or running. After exact
source review, a human repository admin installs it as
.github/workflows/restaurant-linux-verify.yml through the normal GitHub workflow
administration path. The publishing adapter cannot install workflow files; do
not use raw Git or direct broker calls to bypass that installed boundary.
Standard GitHub ubuntu-24.04 supplies the native x64 runner and Docker engine;
no separate self-hosted machine is required. Only manual dispatch is provided.

The narrow host exception requires GitHub-hosted LinuxX64, UID1001 runner,
matching workspace, repository virtualseal/agentwork-promptenglab and immutable
GITHUB_SHA. Local/native checks retain the UID502/path/rootless-engine rules.
Environment checks coordinate trusted execution; they are not an OS sandbox or
authentication mechanism. Do not use them to expose credentials to untrusted code.
The fresh hosted runner receives read-only repository permission, no provider
secrets, and checkout persist-credentials=false. Its Docker socket is never
mounted into the app container. Do not add repository/organization secrets to
this job, secret-bearing runner images, production mounts or deployment steps.

Admin installation/run steps after source publication:
1. In virtualseal/agentwork-promptenglab, use the reviewed source branch.
2. Add the exact template at .github/workflows/restaurant-linux-verify.yml using
   GitHub's admin-approved workflow installation process. No agent merge occurs.
   workflow_dispatch registration must be available on the repository default
   branch to appear in Actions; any required default-branch change is human
   administration, not authorized agent merge/publication.
3. Open Actions -> Restaurant native Linux verification -> Run workflow. Select
   the reviewed branch including the installed workflow. Record its immutable SHA.
4. Confirm the run checks out that exact SHA and all required steps pass. Read
   .review/native-linux/result.json and its invocation-specific operation/check
   logs on the runner if diagnosing a failed job. The workflow prints the result
   and failed-check logs so failure evidence is accessible in Actions.

The checker validates JSON, source cleanliness and final commit identity BEFORE
recording each operation passed. It creates an actual log for both command and
in-process validation operations. Timeout output is saved before draining, and
survives a second drain timeout. Preflight, checks, process-group termination and
exact-invocation container/volume cleanup fit within a14-minute allowance and a
15-minute job. All unexecuted checks remain not_run, and every invocation replaces
stale latest evidence immediately. Failure, missing logs, cancellation and timeout
are not passes. The app's browser and cross-container SQLite outcomes must be
verified; the previous ARM-emulator failure does not satisfy this requirement.

Even CI success leaves ready=false: live Maps refresh from Railway, production
storage, Slack identity/history permissions, broker HTTPS, exact-head review and
explicit rollout authorization remain separate gates. No workflow/service has
been installed or deployed by this source package.
