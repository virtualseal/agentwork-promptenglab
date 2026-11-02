# Personal Railway connection — source prepared, not installed

This supersedes admin/INSTALL.md shared-credential instructions. The Truewind
plugin/OAuth connection and workspace-railway credential are not changed or used.
Only personal-thursday-railway is accepted by tools/railway_deploy.py, which now
allows inspect only; submit/reconcile fail before proxy access. The legacy stage
builder and its dependent installer fail closed. No deployment operation is
registered for the new service. Existing deployment adapter source is historical,
not an activation path. Future deployments require a new reviewed authorization.

railway.connection.json stores non-secret routing only, pinned to project
2d6b15bd-cdab-4978-9518-2d44820cfc85 and repo virtualseal/agentwork-promptenglab.
The environment is intentionally null until the administrator selects it. There
is no global CLI-login or plugin fallback. New service railway-personal uses the
Project-Access-Token header and a single fixed projectToken identity query. It
returns only verified project/environment/repo IDs and connected:true,writes:false.
A token for another project or environment, missing identity, GraphQL failure,
partial HTTP response, missing provider or denial is not success. No retries.
No generic GraphQL,token exposure,account lookup,variable reads or writes exist.

The proxy's project label must equal its existing UID502 namespace (currently
linkedin). This technical namespace label is not the Railway account/project:
the personal integration has a separate protected key entry and provider policy.
All UID502 apps share grants; folder routing prevents mistakes, not hostile apps.
Stronger separation needs separately reviewed OS/service identities and grants.

## Required external admin steps

1. Sign into the personal Railway account. Open this project's Settings -> Tokens
   and create a PROJECT token for the intended environment. Record the environment
   UUID separately; the project URL alone does not identify it. Do not create an
   account/workspace token. Do not paste the token into chat,arguments,source or
   .locals.json. Project-token endpoint compatibility still needs live verification.
2. As agentwork UID502, run the registered tests/evals and stage the pinned package:

       cd /Users/agentwork/apps/thursday-restaurants
       /usr/bin/python3 -B -m admin.prepare_personal_railway .review/personal-railway-stage --environment ENVIRONMENT_UUID

   Replace ENVIRONMENT_UUID with the non-secret selected environment UUID.
   Baseline drift blocks staging. Review the exact generated proxy.patch and policy-addition.json;
   only the personal integration may be added. Full installed config is never copied
   into this app. The admin installer reads it in place and writes only under the
   protected installation/backup paths.
3. Human admin reviews the source manifest and generated stage, then copies only
   the manifest-listed source files (preserving paths),manifest and admin/__init__.py
   into a new root-owned,non-group-writable package directory. Copy no .review,
   .locals.json,local-data,databases,personal settings or existing credentials.
   This protected package must include tools/admin directory layouts. Retain a
   protected copy of the reviewed stage. Never execute mutable agent-owned source
   as a privileged service. No root development/build/test commands are required.
4. Stop the EXISTING credential proxy via its known admin service manager. Its
   service label is not assumed here. Installer refuses a connectable broker
   socket. Preserve the stopped service and its durable state throughout install.
5. From the protected package, human admin runs administration only:

       /usr/bin/python3 -B -m admin.install_personal_railway --stage PROTECTED_STAGE --backup NEW_PROTECTED_BACKUP --environment ENVIRONMENT_UUID

   Run in the human-admin/root administration session. Placeholder paths must be
   real new protected paths. The helper re-stages from pinned bytes and compares
   exact inputs,backs up original proxy/config,then prompts invisibly for the NEW
   project token. It never opens existing key files,changes their bindings or
   restarts a service. Only the new token entry is written,mode0600 owned by503.
   On any partial failure keep the proxy stopped; inspect/recover rather than retry.
6. Verify the installed proxy matches the reviewed patch and that configuration
   has exactly the reviewed personal addition with all other policies unchanged,
   then restart through
   the existing admin service manager. Copy staged railway.connection.json into
   this app as agentwork UID502 and verify its project/environment/integration.
   This step changes reviewed routing bytes: rerun local checks and independent
   review for that exact binding before live inspection. Do not edit the namespace
   to match another account or repoint the integration to an existing token entry.
7. As agentwork UID502, after the exact binding review:

       cd /Users/agentwork/apps/thursday-restaurants
       /usr/bin/python3 -B -m tools.railway_deploy inspect

   Verify project/environment IDs match. This checks a personal project-token
   binding,not plugin identity,service inventory,Slack installation or deployment.
   A missing adapter/key,denial or foreign token must stay blocked without fallback.

No service was stopped/restarted,protected file changed,new key read/installed,
account cross-invited,Slack sent,project setting changed,merge or deploy performed.
The local app has no provider token environment variables. The existing proxy
retains provider credentials; the app receives results only.

## Rollback and interruption

Keep the proxy stopped. Restore original proxy.py/config.json from the new
protected backup only after checking the installed proxy matches the patch and config has only the
reviewed addition;
otherwise investigate additional changes before restoring. Leave the new key
entry and personal_railway.py protected and unused for audit/manual admin cleanup;
never overwrite/delete other credential entries or restore old durable databases.
Restart the original proxy through its known service manager. Existing Truewind
plugin authorization is independent and unchanged throughout.

Tests: python3 -B -m unittest discover -s tests -v and
python3 -B -m unittest discover -s evals -v. Mocked tests verify routing,token
identity mismatch,strict HTTP completeness,project header,mutation rejection,
full transfer receipt,additive staged policy validation and unchanged work policy.
They do not prove live personal Railway access or install the service.

Secure terminal input is mandatory. GetPassWarning becomes an error,so missing
echo control never falls back to visible or redirected token entry. Expanded
mocked installer tests exercise successful additive install,live/unknown socket,
stage/baseline drift,backup failure,insecure input,key/config interruption and
refusal to rerun after partial installation. No privileged operations occur in
tests; synthetic ownership/socket/prompt fixtures isolate temporary directories.

The installer mechanically checks its package root,all ancestors,manifest and
manifest-listed source files are root-owned/non-writable by other users before
opening a socket,prompting or mutating files. Running it as root directly from
the agent-owned checkout is rejected. Package integrity tests verify all four
source manifests,including their dependency hashes,on every test run.
