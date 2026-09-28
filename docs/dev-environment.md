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
2. In one terminal run `make run`; in a second terminal run `make worker` (emails are sent by
   the background worker). Go to `http://localhost:8000/sign-in` and enter a seeded persona's
   email (e.g. `kevin@example.org`). With the console email backend, the sign-in email — code
   and link — prints in the **worker** terminal.
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

## Object storage (S2.4a: requester media uploads, PRD §45, §69)

Dev/test default to the local-filesystem adapter (`HAM_OBJECT_STORE_BACKEND` defaults to
`ham.integrations.storage.local.LocalObjectStore`; files live under `HAM_LOCAL_STORAGE_ROOT`,
default `var/object_storage/`, gitignored). Nothing to configure for `make run`/`make test`.

Production uses Cloudflare R2 (S3-compatible). Set:

```
HAM_OBJECT_STORE_BACKEND=ham.integrations.storage.s3.R2ObjectStore
HAM_S3_BUCKET=<bucket name>
HAM_S3_ENDPOINT_URL=https://<account id>.r2.cloudflarestorage.com
HAM_S3_REGION=auto
HAM_S3_ACCESS_KEY_ID=<R2 access key id, from the secret store>
HAM_S3_SECRET_ACCESS_KEY=<R2 secret access key, from the secret store>
```

### Bucket setup runbook (one-time, per environment)

1. **Create the bucket** in the Cloudflare dashboard (R2 → Create bucket). One bucket per
   environment (e.g. `ham-media-prod`); never share a bucket between prod and a staging/dev
   deployment.
2. **CORS**, so a requester's browser can PUT directly to a presigned URL from
   `HAM_BASE_URL`'s origin (`ham.media`'s upload flow, S2.7's client-side upload module):
   ```json
   [
     {
       "AllowedOrigins": ["https://<your HAM_BASE_URL host>"],
       "AllowedMethods": ["PUT", "GET"],
       "AllowedHeaders": ["content-type"],
       "MaxAgeSeconds": 3600
     }
   ]
   ```
   Do not use `"AllowedOrigins": ["*"]` in production — that would let any site's script
   upload to a presigned URL a HAM user's browser was handed (the URL itself is still
   short-lived and single-key, but CORS is a second, free layer of defense).
3. **Lifecycle rule**: delete objects under `quarantine/` (the original, pre-processing
   upload — `ham.media`'s processing job deletes these itself once re-encoding finishes, Q-120
   "delete originals, serve only HAM-made copies") after **2 days** if the job never ran (a
   stuck/crashed worker, or a reservation that was never completed) — a safety net, not the
   primary deletion path. Add a bucket lifecycle rule scoped to the `quarantine/` prefix,
   "Expire objects", 2 days. Do not add a lifecycle rule under the `media/` prefix (processed,
   served derivatives) — their retention is `ham.media`'s own retention-sweep job (§47,
   Q-128), driven by request/project state, not a fixed bucket-wide clock.
4. **No public bucket access.** Every read goes through `presign_get` (short-lived, per-key);
   there is no "public bucket" or CDN mapping in V1 (§48 public-use consent is deferred,
   CLAUDE.md scope).
5. **Access keys**: create one R2 API token scoped to *only* this bucket (Object Read & Write),
   not an account-wide token. Store `HAM_S3_ACCESS_KEY_ID`/`HAM_S3_SECRET_ACCESS_KEY` in
   Render's secret store, never in `render.yaml` or committed anywhere (CLAUDE.md "secrets
   come from environment variables").

## Common commands

See the Makefile: `make install`, `make migrate`, `make run`, `make worker`, `make test`,
`make lint`, `make tokens`.
