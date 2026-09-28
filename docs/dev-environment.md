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

# S3b auth: encrypts TOTP secrets at rest (ham.identity.crypto). Optional in dev/test (falls
# back to a key derived from DJANGO_SECRET_KEY); required in production. Generate a real one
# with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Web and worker must use the exact same value (render.yaml wires the worker's from the
# web service's, rather than a second independently-typed secret) -- the worker decrypts
# background-job payloads (security review C2), and losing/rotating this key makes every
# already-enrolled TOTP secret/recovery code (and every trusted-device cookie, which is
# itself HMAC-signed with DJANGO_SECRET_KEY -- rotating *that* key has the same effect)
# undecryptable/invalid, forcing an MFA reset for everyone.
HAM_FIELD_ENCRYPTION_KEY=

# Emailed links (invitations, role-change/impersonation-ended notices) are built from this.
# Required (and must not be localhost) in production; safe to leave unset in dev (falls back
# to http://localhost:8000).
HAM_BASE_URL=http://localhost:8000

# Security review round 3, N5: how many X-Forwarded-For hops (right-to-left) were added by
# proxies HAM itself controls -- 0 (the default) means "no proxy in front, trust
# REMOTE_ADDR only"; Render's edge proxy adds exactly one hop (render.yaml sets this to 1).
HAM_TRUSTED_PROXY_COUNT=0
```

## Signing in locally (S3b)

1. `make dev-db && make migrate && python manage.py seed_dev` (refuses if `HAM_ENV=production`).
2. `make run`, go to `http://localhost:8000/sign-in`, enter a seeded persona's email
   (e.g. `kevin@example.org`). With the console email backend, the sign-in email — code and
   link — prints to the terminal running `make run`.
3. Non-MFA personas (Kevin, Tom, Luis, Grace, Bayside Plumbing) land straight on Home.
4. MFA personas (Nadia, Marcus, Andre, Ruth, Samuel — PRD §60.1) are asked for a code from an
   authenticator app after the email step. `seed_dev` prints each persona's fixed dev-only
   TOTP secret; get a current 6-digit code any time with:
   ```
   python manage.py dev_totp nadia@example.org
   ```
   (refuses outside development, same as `seed_dev`).

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
