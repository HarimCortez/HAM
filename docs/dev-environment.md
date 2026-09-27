# Local development environment

Create your own `.env` in the repo root (never committed — see `.gitignore`) with:

```
DJANGO_SETTINGS_MODULE=config.settings.dev
DJANGO_DEBUG=true
DJANGO_SECRET_KEY=dev-insecure-secret-key-change-me
HAM_ENV=development

# Q-026: selects design-system/brands/<id>/
HAM_BRAND=miami-temple

# postgresql://<user>:<password>@<host>:<port>/<dbname>
DATABASE_URL=postgresql://ham:ham@localhost:5432/ham_dev

DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# Console backend in dev: sign-in codes print to the terminal instead of sending real email.
DJANGO_EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
DEFAULT_FROM_EMAIL=no-reply@example.org
```

(`.env.example` isn't checked in: this sandbox's `.claude/settings.json` denies reading/writing
any `.env*` path, including `.env.example`, as a secrets guardrail. Copy the block above
instead — nothing in it is a real secret.)

## Postgres

`make dev-db` starts a local Postgres 16 cluster under `./pgdata` (gitignored) using
`scripts/dev_db.sh`, on the unix socket with trust auth so no password juggling is needed
locally, and creates the `ham_dev` and `ham_test` databases.

```
make dev-db      # first time: initdb + start + createdb
make dev-db-stop # pg_ctl stop
```

## Common commands

See the Makefile: `make install`, `make migrate`, `make run`, `make worker`, `make test`,
`make lint`, `make tokens`.
