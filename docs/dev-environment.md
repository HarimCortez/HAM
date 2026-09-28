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

## Email in production (`ham.integrations`, foundation.md §8 S4)

Production selects an Anymail ESP backend and its settings entirely from the environment —
never hard-coded (CLAUDE.md "Secrets come from environment variables or a secret store").
Example for Postmark (any Anymail-supported ESP works the same way):

```
DJANGO_EMAIL_BACKEND=anymail.backends.postmark.EmailBackend
ANYMAIL_SETTINGS_JSON={"POSTMARK_SERVER_TOKEN": "<secret, from the secret store>"}
```

`ANYMAIL_SETTINGS_JSON` is parsed as JSON into Django's `ANYMAIL` setting
(`config/settings/base.py`). Dev and test never read it (console/locmem backends).

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
