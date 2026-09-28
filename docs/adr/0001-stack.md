# ADR 0001: Technology stack and hosting

- **Status:** Accepted (product owner, 2026-09-27). Answers Q-003.
- **Date:** 2026-09-27
- **Drafted by:** ham-architect
- **PRD:** §3, §7, §35, §36.1, §58–§60, §69, §70, §73, §75, §77, §78

> **Check-current notice.** Prices and library facts below were checked on 2026-09-27 and will change. Before deciding, re-check them at the links in "Sources to verify". Do not treat the dollar figures as quotes.

## 1. Context
HAM is a web app for one church's Men's Ministry. The owner builds it alone with AI agents, has little coding experience, and has no one to patch servers. The ministry is unpaid, so monthly cost must stay low. The app needs:
- a relational database (§78) with append-only audit data (§58);
- background jobs for reminders, waitlists, retention and calendar sync (§78);
- an installable PWA with an **offline check-in queue** (Q-006) and QR/GPS check-in (§37);
- email sign-in for everyone (§60.2, Q-019: email only), **TOTP MFA** for privileged roles (§60.1), a 30-day trusted device and step-up re-checks (Q-010);
- administrator impersonation (§59) and requester secure links (§7);
- email plus in-app notifications (§35), Google Calendar sync (§51), and private object storage with video compression (§45, §69, §78);
- easy backups, a full end-to-end test of the §77 scenario, and the ability for another church to deploy its own copy with only configuration changes (Q-026).

## 2. Decision drivers (most important first)
1. **Security we don't have to write ourselves.** Sign-in, MFA, sessions and CSRF protection should come from mature, widely used libraries (§3.4, §60).
2. **Minimal operations.** Managed database and hosting, no servers to patch, and one-click redeploys.
3. **Boring and well documented.** A stable framework that AI agents generate correct code for, with few breaking changes per year.
4. **Low monthly cost** at about 100 users.
5. **Offline PWA fit** for check-in on project day.
6. **Testability,** including Playwright end-to-end tests and time travel for rules like "48 hours before".
7. **Easy to copy** for another church (Q-026).

## 3. Options

### Option A: TypeScript full stack
| Aspect | Choice |
|---|---|
| Language / framework | TypeScript; Next.js (App Router) or React Router 7; Drizzle ORM |
| Database | Managed Postgres |
| Auth / MFA | Better Auth (email OTP / magic link, `twoFactor` TOTP with trusted device, `admin` plugin with impersonation) |
| Jobs | pg-boss (Postgres-backed queue with cron schedules), as a separate worker process |
| Email | Resend or Postmark API |
| Hosting | Render web service + background worker + Render Postgres (Vercel does not fit long-running workers) |
| Cost (~100 users) | About $20–37/month (see §4) |
| Ops burden | Low on a PaaS. **High dependency churn**: frequent major releases of the framework and auth library, so agents often write outdated patterns |
| Backups | Provider point-in-time recovery plus a nightly `pg_dump` to off-site storage |
| Offline PWA fit | **Best.** The same language on client and server; Workbox/Serwist service worker; shared types for the queued check-in payload |
| Testability | Vitest + Playwright (native). The §77 scenario runs well |
| Key risk | Better Auth issue #11287 (open at the time of writing): the `twoFactor` challenge **does not fire after magic-link or email-OTP sign-in**, which is exactly HAM's sign-in method. Working around it means hand-writing security-critical session code. |

### Option B: Django + HTMX (recommended)
| Aspect | Choice |
|---|---|
| Language / framework | Python 3.12+, **Django 5.2 LTS** (security support to April 2028; move to the next LTS, 6.2, after its release). Server-rendered pages with HTMX. One small TypeScript bundle (esbuild) for the service worker, the offline check-in queue and the QR scanner |
| Database | Managed Postgres (sessions and job queue also in Postgres, so no Redis) |
| Auth / MFA | **django-allauth**: login by emailed code (`ACCOUNT_LOGIN_BY_CODE_*`), MFA with TOTP + recovery codes, "trust this browser" (`MFA_TRUST_ENABLED`, `MFA_TRUST_COOKIE_AGE` = 30 days, `ACCOUNT_LOGIN_BY_CODE_TRUST_ENABLED`), reauthentication for step-up, built-in rate limits. HAM adds (a) mandatory-MFA enforcement for the §60.1 roles, (b) impersonation (§59) as a small in-house module, and (c) a one-click sign-in link alongside the code (spike; fallback is codes only) |
| Jobs | **Procrastinate** (Postgres-backed, retries, periodic/cron tasks, Django integration) behind a thin `ham.jobs` interface. Django 6's built-in tasks API ships no production worker, so it is not enough on its own |
| Email | django-anymail → Resend (free tier) or Postmark (paid), swappable by setting |
| Hosting | Render: Docker web service + background worker + Render Postgres; `render.yaml` blueprint |
| Cost (~100 users) | About $20–37/month (see §4) |
| Ops burden | **Lowest.** Slow, predictable releases; LTS line; batteries included (ORM, migrations, forms, CSRF, sessions) |
| Backups | Render point-in-time recovery (3 days on the Hobby workspace, 7 on Pro) plus a nightly `pg_dump` job to off-site object storage, kept 35 days, with a documented restore drill |
| Offline PWA fit | Good. Pages are server-rendered and the service worker caches the app shell and recent pages (read-only when offline). Check-in/out is queued in IndexedDB by the TypeScript module and sent when the device reconnects (on `online` and on app open, because iOS lacks Background Sync). Two languages, but the offline part is small and isolated |
| Testability | pytest + pytest-django + factory_boy + time-machine; **Playwright for Python** (`pytest-playwright`) against Django's `live_server`. Emails are captured by the in-memory mail backend, and Calendar is a fake adapter. The §77 scenario is one long e2e test |
| Key risks | Procrastinate has a smaller community than Celery (mitigated by the `ham.jobs` interface). allauth sends codes, not one-click links, so the link needs a small custom addition. Django's built-in admin bypasses HAM's authorization and audit, so it must be off in production |

### Option C: Rails 8 + Hotwire
| Aspect | Choice |
|---|---|
| Language / framework | Ruby, Rails 8, Hotwire (Turbo/Stimulus) |
| Database | Managed Postgres |
| Auth / MFA | rodauth-rails (email auth, OTP, recovery codes, remember), which is powerful but has a steep configuration curve. The Rails 8 auth generator is password-only |
| Jobs | Solid Queue (database-backed, recurring jobs), built in |
| Email | Action Mailer → Postmark/Resend |
| Hosting | Render (as B), or Kamal to a VPS (rejected: server patching) |
| Cost (~100 users) | About $20–37/month |
| Ops burden | Low on a PaaS. Rails 8 is very complete |
| Backups | Same as B |
| Offline PWA fit | Fair. Rails 8 generates a manifest and service worker; the offline queue is custom JavaScript |
| Testability | Minitest/RSpec + Capybara with a Playwright driver |
| Key risks | Ruby has a smaller share of AI training data and a smaller local help pool; rodauth complexity |

### Comparison
| Driver | A: TypeScript | **B: Django** | C: Rails |
|---|---|---|---|
| Mature auth + MFA after email sign-in | Weak (open issue) | **Strong** | Good (complex) |
| Low churn / boring | Weak | **Strong** | Strong |
| AI agents build it well | Strong | **Strong** | Medium |
| Offline PWA | **Strong** | Good | Fair |
| Jobs without Redis | Good | Good | **Strong** |
| Monthly cost | Same | Same | Same |
| E2E / Playwright | **Strong** | Strong | Good |

## 4. Hosting and cost (same shape for every option)
| Item | Choice | Approx. monthly |
|---|---|---|
| Web app | Render web service "Starter" (0.5 CPU, 512 MB) | $7 |
| Background worker | Render background worker "Starter" | $7 |
| Database | Render Postgres Basic-256MB (move to Basic-1GB at $19 if needed) | $6 (–$19) |
| Workspace | Render Hobby workspace | $0 |
| Email | Resend free (3,000/month, **100/day cap**) or Postmark Basic (10,000/month) | $0 or $15 |
| Object storage + off-site backups | Cloudflare R2 or Backblaze B2 (needed from step 2) | about $0–2 (verify) |
| Domain | Church subdomain (e.g. `ham.<church>.org`) | $0 if the church owns the domain |
| **Total** | | **about $20–37/month** |

Notes:
- Render's free web and database tiers are for experiments and are not suitable for production.
- The Resend daily cap could block sign-in codes on a heavy invitation day. Move to a paid plan once a typical day exceeds about 60 emails. HAM talks to email only through an adapter, so switching provider is a settings change.
- Email must be authenticated (SPF, DKIM, DMARC) on the sending domain. This is an owner/IT task.
- A single $6 VPS was rejected: someone would have to patch it.

## 5. Recommendation
**Option B: Django 5.2 LTS + Postgres + HTMX, a small TypeScript offline module, Procrastinate jobs, django-allauth, hosted on Render.** Reasons:
1. The most security-sensitive parts (email-code sign-in, TOTP, recovery codes, 30-day trusted browser, reauthentication, rate limiting) come from one mature library. Option A's leading auth library currently skips MFA after exactly the sign-in method HAM uses.
2. It has the fewest moving parts: one app, one database (also used for sessions and jobs), no Redis, no separate front-end app.
3. The framework changes slowly and has a long-term-support line, which suits a solo owner working with AI agents.
4. The offline check-in queue is the one place that needs rich client code, and it is small enough to isolate in a TypeScript module.
5. Another church deploys its own copy with the same `render.yaml` blueprint, its own `design-system/brands/<id>/` folder and the `HAM_BRAND` setting (Q-026).

## 6. Consequences
- **Positive:** Mature security defaults. Low ops. About $20–37/month. The §77 scenario is testable in one Python e2e test with fake adapters. One-click redeploy for another church.
- **Negative:** Two languages (Python, plus a little TypeScript; Node is used only at build time). HTMX suits pages and panels, not very rich client apps; HAM doesn't need one. The Procrastinate community is smaller than Celery's.
- **Guardrails that follow from this ADR:**
  - Django's built-in admin is **not mounted in production**, because it would bypass HAM's authorization and audit.
  - Every write goes through HAM's command layer (see `docs/architecture/foundation.md`).
  - Docker deploys, so ffmpeg is available for video compression (§45).
  - Postgres is the only stateful service.
- **Follow-ups:**
  - Fill in the CLAUDE.md commands:
    - Install: `uv sync && npm ci`
    - Test: `uv run pytest`
    - Lint/typecheck: `uv run ruff check . && uv run ruff format --check . && uv run mypy . && npx tsc --noEmit`
    - Migrate: `uv run python manage.py migrate`
    - Dev URL: `http://localhost:8000`
  - Mark Q-003 "see ADR 0001".
  - Re-check prices before signing up.

## 7. In plain language for the owner
- All three choices cost about the same (roughly $20–37 a month), so the choice is about safety and upkeep.
- We recommend **Django**, a Python tool that has been around for almost 20 years and changes slowly.
- Its sign-in add-on already handles emailed codes, authenticator-app codes and "trust this device for 30 days". We don't have to invent security.
- The main alternative's sign-in add-on currently has a known flaw that would skip the second sign-in check for leaders.
- Render runs the servers and database for us: no patching, automatic database backups, and a nightly extra copy stored elsewhere.
- The phone app (PWA) will still record check-ins with no signal and send them later.
- Another church can run its own copy by swapping a logo/colour folder and a few settings. No code changes.
- Trade-off: a small part (offline check-in) is written in a second language. The agents handle that.
- You decide. If you approve, we mark this ADR "Accepted" and start step 1.

## 8. Sources to verify (checked 2026-09-27)
- Render pricing (web $7, worker $7, Postgres Basic-256MB $6, PITR 3/7 days): https://render.com/pricing
- Railway pricing (alternative host): https://docs.railway.com/reference/pricing/plans
- Postmark pricing ($15 / 10,000 emails): https://postmarkapp.com/pricing
- Resend pricing (free 3,000/month, 100/day): https://resend.com/pricing
- Cloudflare R2 pricing (not verified in this draft): https://developers.cloudflare.com/r2/pricing/
- Django support dates: https://endoflife.date/django
- django-allauth MFA settings: https://docs.allauth.org/en/dev/mfa/configuration.html
- django-allauth login-by-code settings: https://docs.allauth.org/en/dev/account/configuration.html
- Django 6 tasks have no production worker: https://www.loopwerk.io/articles/2026/django-tasks-review/
- Procrastinate: https://procrastinate.readthedocs.io/
- Better Auth 2FA issue: https://github.com/better-auth/better-auth/issues/11287

## Amendment 2026-09-28: two-step sign-in uses pyotp + HAM's own flow instead of allauth.mfa

Status: Accepted (implemented by ham-backend-engineer, in response to the step-1
privacy/security review).

S3b's own build note (§6/§7 above; `docs/prd-open-questions.md` Q-085) already explains why
`allauth`/`allauth.mfa` was never wired in as a Django app: doing so pulled the separate,
legacy top-level `allauth` app's own `EmailAddress`/`EmailConfirmation` models into Django's
unmigrated-app table sync, breaking test-database creation. The fallback at the time was to
hand-implement RFC 6238 (HMAC-SHA1 over a 30-second time counter) directly against
`hmac`/`hashlib`.

The privacy/security review flagged that hand-written construction as exactly the kind of code
CLAUDE.md/PRD §3.4-§3.5 want out of application code: real cryptographic-adjacent logic, with
no independent security review, that happened to look small. This amendment replaces it with
[`pyotp`](https://pypi.org/project/pyotp/), an independently maintained, widely used TOTP/HOTP
library, while keeping HAM's own sign-in/enrollment/step-up flow (still not `allauth.mfa`'s
pipeline, for the same reasons as before) and HAM's own tables (`TOTPDevice`, `RecoveryCode`,
`TrustedDevice`).

Because of this swap, `django-allauth` is no longer a project dependency at all (previously it
was kept only for its `qrcode` transitive package); `qrcode` is now a direct dependency.

Mitigations that shipped alongside the swap (also from the security review):
- **Replay protection**: `TOTPDevice.last_used_step` records the highest 30-second counter
  step already accepted; verification runs under `select_for_update()` and refuses to accept a
  step at or before that value, so a captured/observed code can't be replayed.
- **Attempt limits**: both the sign-in MFA challenge and the "Confirm it's you" step-up screen
  now lock out after `RULES.auth.MFA_CODE_MAX_ATTEMPTS` wrong tries (Q-072), audited.
- This change, and the review that motivated it, are recorded here rather than only in code
  comments so a later slice doesn't re-attempt wiring the same allauth apps without re-reading
  this note (Q-085 stays open for that reason).
