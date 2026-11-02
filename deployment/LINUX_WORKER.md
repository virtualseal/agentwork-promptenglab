# Linux worker package — local build, not activated

The worker Dockerfile pins the official Playwright 1.60.0 Ubuntu Noble amd64
browser image by digest and installs the matching Python package as UID502.
Only account/directory provisioning runs as root during image construction;
application installation and execution run as agentwork502. Source COPY paths
and the Dockerfile-specific ignore file exclude admin broker code, Git, local
saved places, credentials and historical state. Never add provider credentials
to build arguments or this worker's environment.

The cloud config preserves Thursday17:00 America/Los_Angeles, Want to go only,
ten straight-line miles and channel C0CCRQUR6G1. Its browser interpreter exists
inside the image. Both snapshot and weekly SQLite/lock paths are under
/data/worker. An administrator must provide a writable persistent volume for
UID502 and exactly one replica. Restart must reuse that same volume. The image
contains no real saved-place snapshot: live mode refreshes the configured public
list before each new weekly choice, after separate activation.

The packaged config deliberately remains preview with live_reviewed=false.
Readiness stays503. This is not a deployed or ready-to-send application. Do not
change health checks merely to claim activation. Slack broker hosting/HTTPS,
scoped capability, workspace identity, permission checks, real cloud storage
and explicit deployment/activation authorization remain required. Keep the
existing market-briefing-scheduler untouched; a token being present there is
not permission to copy it into this worker.

Local build (agentwork502; use this project's dedicated Docker endpoint):

    python3 -B deployment/build_linux_worker.py --host unix:///Users/agentwork/.colima/restaurant-build/docker.sock

The builder stages only explicit regular source files and rejects symlink escapes.
Do not pass the private checkout root as a Docker context; older builders may
ignore Dockerfile-specific exclusion files. The image also pins transitive
package versions. Run the real offline browser/storage checks after building:

    python3 -B deployment/verify_linux_worker.py --host unix:///Users/agentwork/.colima/restaurant-build/docker.sock
 Stop/start
of the project VM uses COLIMA_HOME=/Users/agentwork/apps/thursday-restaurants/.review/build-runtime/colima
and `colima stop restaurant-build` / `colima start restaurant-build` respectively.
The default Docker context remains unchanged. No automatic VM startup is installed.

Official references: https://playwright.dev/python/docs/docker and
https://docs.railway.com/builds/dockerfiles. Their examples are documentation,
not permission to run as root or deploy. Railway must use the specific worker
Dockerfile and reviewed immutable revision; no Railway service was changed.

Current local evidence: the amd64 image builds, but its Chromium process crashed
under QEMU on this ARM Mini. That is a failing required runtime check, not a
pass or a waiver. Run the same verifier on a native Linux/amd64 engine before
marking the package ready. Do not change the architecture, skip the browser
check or weaken the security options to obtain a passing result. Product unit
tests and acceptance evals remain separate evidence.
