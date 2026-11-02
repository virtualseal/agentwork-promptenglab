# Personal project service discovery — prepared, not installed

The installed connection proved only project/environment identity. This upgrade
adds service discovery to the same read-only connection.inspect operation,after
identity verification. It stays bound to project2d6b15bd-cdab-4978-9518-2d44820cfc85
and environmentb862c0ae-b2e6-430f-9abf-5e55b4ba1e66. It does not grant access to
other projects or the whole personal account; a project token cannot do that.
The globally connected Truewind plugin remains untouched and is not a fallback.

The fixed environment query returns service IDs,names and latest deployment
status only. It never reads variables/tokens/logs or changes services. Foreign
identity/environment,incomplete pagination,duplicates and malformed records fail
closed. Live GraphQL compatibility remains unverified until admin installation.
The same installed project token is reused by the protected proxy; no new token
entry or credential file is read/copied/changed by this upgrade helper.

Human admin must copy the independently reviewed standalone
admin/upgrade_personal_discovery.py into the root-owned CredentialProxy directory
before execution. The helper rejects agent-owned execution even as root. It
checks the old installed adapter and new source SHA256 plus exact personal
policy scope,backs up only old source,stops system/local.credential-proxy,
rechecks unchanged source/config,atomically replaces ONE source module,verifies
configuration is byte-for-byte unchanged,and restarts the existing proxy.
If stop/restart has unknown outcome,inspect service state; never rerun blindly.
If any failure happens after stop,leave it stopped for inspection. No deployments
or Slack sends occur. Existing root service identity is apiproxyUID503.

After installation,as agentworkUID502:

    cd /Users/agentwork/apps/thursday-restaurants
    /usr/bin/python3 -B -m tools.railway_deploy inspect

This discovers the user's actual services without asking them to identify IDs.
It does not prove Slack connectivity or activate the weekly schedule. Those and
explicit deployment authorization remain separate gates.

Shutdown timing recovery: bootout can return before the socket stops accepting.
The helper now waits up to ten seconds for connection refusal before replacing
source. Unexpected socket errors and an expired deadline fail closed. If the
old helper failed at this check, inspect service/socket state and adapter hash.
After confirming the service is stopped and old adapter remains, human admin
may install the updated reviewed helper and run it with --resume-stopped.
That explicit recovery checks protected original source backup equality, current
old/new hashes and unchanged exact policy scope, never repeats bootout, and
requires a refusing socket before replacement. No backup deletion or credential
access is needed. An already replaced module still refuses this recovery.
