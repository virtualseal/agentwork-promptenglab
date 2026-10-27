# LinkedIn Agent: native local runtime

Read ../AGENTS.md. Run development and runtime as agentwork UID 502 under
/Users/agentwork/apps. CLAUDE.md is a relative symlink to this file.

## Ownership and contracts

app/main.py owns FastAPI routes; app/writing owns prompt orchestration;
app/llm owns the provider boundary. POST /generate accepts a topic (5–500
characters) and returns text, model, input_tokens, output_tokens. Provider and
proxy failures return HTTP 502 without exposing provider error details.
GET /health is liveness only; it does not call the proxy or prove generation.
There is no database code or persistence in the current app.

app/llm/claude.py uses the protocol-v2 Unix-socket broker through
app/llm/proxy_client.py (copied client matches the installed client at review).
Read /Users/agentwork/PROXY-ACCESS.txt and installed non-secret policy before
changing integration behavior. Socket:
/Library/Application Support/CredentialProxy/run/api.sock.
Integration linkedin-anthropic, operation messages.create, default model
claude-sonnet-4-5. Optional ANTHROPIC_MODEL must be allowed by installed policy.
No provider keys or .env files are needed. Never bypass proxy denial.
linkedin-anthropic is live; mock tests by default, no paid checks without explicit
authorization or an agreed budget. All UID 502 apps share grants and quotas.

## Setup, run, and verification

From /Users/agentwork/apps/linkedin-agent, after verifying id -un and id -u:

```
python3 -m venv .venv
.venv/bin/python -m pip install -r app/requirements.txt
.venv/bin/python -B -m unittest discover -s tests -v
.venv/bin/python -B -m unittest discover -s evals -v
./run
```

The foreground launcher checks UID 502 before runtime and binds 127.0.0.1:8000.
Stop with Ctrl-C. No scheduled startup is configured. Check liveness from another
terminal with `curl --fail http://127.0.0.1:8000/health`; use /docs to inspect the
API. POST /generate makes a paid live request; tests patch the provider boundary
and must not contact the installed live service. httpx supports TestClient.

compose.yaml and app/Dockerfile are transferred references, not the native
startup path. Compose still references an obsolete direct key; do not launch it,
load old shared secrets, grant Docker privileges, or migrate databases. Native
startup requires no PostgreSQL for current routes. Existing shared launchers
have not been retrofitted.

## Review and merge readiness

evals/test_acceptance.py owns offline product scenarios: representative topics,
input boundaries, Unicode, preservation of system/user role separation and
voice constraints, response/usage contract, no provider calls for rejected
input, and sanitized failure responses. These evals mock provider results;
they do not grade actual generated post quality or prove resistance to prompt
injection. Live writing-quality evaluations need an explicitly agreed budget.

The shared controller runs tests/evals plus a separate reviewer before merging
the exact published head through protected GitHub gates. LinkedIn is not yet
registered: it needs a reviewed Git import, CI bootstrap and synchronized local
baseline first. The human-reviewed CI template is at
../credential-admin/templates/linkedin-verify.yml. Agents cannot install/change
GitHub workflows through the publishing adapter. Configure GitHub's required
agentwork-verify check with the trusted Actions app and strict admin-enforced
protection. See ../dev-controller/AUTO-MERGE.md for activation.

The controller stays on the Mini; the user owns Railway GitHub auto-deploy.
The app still depends on the Mini's Unix socket. Merging code does not make that
socket available in Railway or prove cloud generation works. Do not replace
proxy denial with direct provider keys.

See README.md and the review/merge readiness section above for current setup
and remaining import/cloud-provider requirements. Local historical handoffs are
excluded from the published source.
