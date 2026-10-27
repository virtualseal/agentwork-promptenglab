# LinkedIn Agent

FastAPI backend for generating LinkedIn posts through the installed credential
proxy. The app receives results, never provider keys. There is no database.

From an agentwork UID502 session on the Mini:

```
cd /Users/agentwork/apps/linkedin-agent
.venv/bin/python -B -m unittest discover -s tests -v
.venv/bin/python -B -m unittest discover -s evals -v
./run
```

The existing environment is reused. See AGENTS.md for initial setup. Native
startup binds 127.0.0.1:8000 after an early UID502 check. GET /health is liveness;
POST /generate accepts a topic of 5–500 characters and returns text, model,
input_tokens and output_tokens. Generation makes a paid provider request; tests
and acceptance evals mock that boundary. No live content-quality evaluation is
claimed by those checks.

The controller stays on the Mini and can merge only after tests, separate evals,
independent review and protected GitHub gates pass. Repository import, trusted
GitHub CI/protection, and controller registration must be completed first.
The CI template in ../credential-admin/templates/linkedin-verify.yml is for
human-admin installation; agents cannot change CI workflows through the proxy.

The user configures Railway GitHub auto-deploy. This source still depends on
the Mini-local Unix socket, which Railway cannot access as a local file. A
cloud-compatible approved provider connection is needed before cloud generation
can work. No direct provider-key fallback is supported. A healthy cloud web
server alone would not establish successful generation.

The transferred compose.yaml and app/Dockerfile are ignored migration references,
not approved deployment instructions. No databases, secrets or local environments
are part of the source import.
