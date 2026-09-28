# HAM — Home Assistance Ministry

Web app that manages a church Men's Ministry's home-assistance projects, from request to completed service.

- Product requirements: [`docs/HAM_PRD_V1.md`](docs/HAM_PRD_V1.md) (source of truth)
- Project rules for Claude and the agent team: [`CLAUDE.md`](CLAUDE.md)
- How the 11-agent team works: [`SETUP.md`](SETUP.md)
- Open product questions: [`docs/prd-open-questions.md`](docs/prd-open-questions.md)

Status: build-order step 1 (platform skeleton) in progress. Stack: Django 5.2 LTS + Postgres +
HTMX on Render (`docs/adr/0001-stack.md`, Accepted).

## Getting started

```
make install   # uv venv + deps
make dev-db    # local Postgres 16 cluster (no Docker needed)
make migrate
make run       # http://localhost:8000/healthz
make test
make lint
```

See [`docs/dev-environment.md`](docs/dev-environment.md) for the `.env` you need and
[`docs/architecture/foundation.md`](docs/architecture/foundation.md) for the module map.
