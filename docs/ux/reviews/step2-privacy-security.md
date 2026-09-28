# Step 2 (Intake): privacy and security review (ham-privacy-security-reviewer)

**Scope:** `git diff main...HEAD` on `feature/step-2-intake` at `1ffe291`. The reviewer is read-only and has no Write tool, so the orchestrator saved this report. It follows the reviewer's findings and keeps the same IDs. Two proof-of-concept tests were run from a scratchpad; no application files were changed.

**Summary:** Critical: none. High: 4. Medium: 6. Low: 8.

## High

### H1. The emailed code is not tied to the draft or the email that gets submitted
- **Refs:** PRD §7.1, §6, §77; Q-100.
- **Where:**
  - `verification.py:191-223`: `verify_code` matches the challenge by `email_key` and purpose only.
  - `views_requester.py:298`: wizard steps can still be saved after the code is sent.
  - `views_requester.py:514-521`: the draft submitted is the one named in the cookie.
  - `services.py:381-440`: the challenge and the draft are never compared, and `verified_value` comes from the draft's current email.
- **Proof of concept:**
  1. Send a code to the attacker's own address A.
  2. POST the "reaching you" step again with the victim's address.
  3. POST A's code.
  4. Result: a request is stored with the victim's email, "Email confirmed" is recorded for the victim's address, and the victim is emailed.
- **Fix:**
  - `submit_and_issue_link` requires that the challenge purpose is intake, that the challenge is consumed, that `challenge.draft_id` is this draft, and that `challenge.email_key` is the hash of the submitted email.
  - Set `verified_value` from the verified address.
  - A verification can be used for only one submit.
  - `_after_verified` uses `challenge.draft_id`.
  - Editing the email after a code has been sent invalidates any outstanding challenges.

### H2. "Find my request" plus the hourly code cap reveals whether an email has a request
- **Refs:** PRD §68; Q-121.
- **Where:**
  - `services.py:257-272`: find-my-request sends one code per matching request.
  - `verification.py:140-145`: the cap is shared across all purposes.
  - `views_requester.py:394-399`: a distinct "can't send more codes" message.
- **Proof of concept:**
  1. Run 5 finds for the target address.
  2. Press Send on the intake form with the same address.
  3. The error appears only if a request exists.
- **Fix:** identical UI for sent, cooldown and rate-limited results (the cap sends nothing, silently); separate budgets per purpose; enforce the per-IP find limit.

### H3. The free-text close note goes into the redirect URL
- **Refs:** PRD §68, §51.1.
- **Where:** `views_requests.py:347-349`, echoed back at lines 364-365.
- **Impact:** the note ends up in the Location header, access logs, browser history and Referer, and it isn't URL-encoded.
- **Fix:** re-render with a 422 and the posted values; never put free text in the query string.

### H4. Every requester email links to a 404
- **Refs:** PRD §7.2, §7.3; Q-102.
- **Where:** `notifications.py:59` builds `/r/<token>`, but the route is `/request-help/r/<token>`.
- **Fix:** use `reverse("web:request_help_secure_page", ...)` and test that the emailed URL resolves.

## Medium
- **M1. The Q-121 limits are defined but never enforced.**
  - `INTAKE_SUBMISSIONS_PER_EMAIL_PER_DAY` and `FIND_REQUEST_TRIES_PER_IP_PER_HOUR` are never read.
  - There is no per-IP cap on sending codes, so one draft can relay codes to any number of addresses.
  - The no-email path can flood leaders with urgent banners.
  - Fix: enforce both rules, add a per-IP send cap, and cap no-email submissions per phone and per IP (Q-146).
- **M2. The presigned PUT has no size limit, and the worker loads the whole object** (`s3.py:59-75`, `media/jobs.py:66`).
  - Fix: sign `ContentLength`, and check the size with `head()` before `get_object`.
- **M3. Originals with GPS data can stay in quarantine forever, and reserved slots never free up.**
  - `MEDIA_UPLOAD_INTENT_LIFETIME` is never read.
  - Fix: a periodic sweeper for stale reserved, uploaded and processing items; delete the quarantine objects and audit it.
- **M4. The spam purge leaves media files in storage** (`requests/services.py:546-555`: `request.delete()` removes the rows only).
  - Fix: purge the storage objects through a media service first.
- **M5. Production config doesn't require the token HMAC key or the object-store settings.**
  - `/dev/storage/` is mounted unconditionally.
  - Fix: fail fast in `prod.py`, add the variables to `render.yaml`, and mount the dev storage route outside production only.
- **M6. `requester_verification.locked` is never audited.**
  - Fix: audit when a challenge hits the maximum attempts and when the daily cap trips (no address in the event).

## Low
- **L1. JPEG comment (COM) segments survive re-encoding** (`processing.py:98-107`).
  - Fix: strip the comment; apply `exif_transpose` first.
- **L2. Reveal on a NEEDS_PHONE_CHECK request by UUID** (`requests/services.py:485`).
  - The lookup is unscoped, so the reveal is audited before the page returns 404, and an unknown id gives a 500.
  - Fix: scope the lookup first.
- **L3. Uploading automatically opens a new batch** once all batches are closed (latent until step 3).
  - Fix: only ever auto-create batch #1.
- **L4. Old tokens of a spam-purged request give a 500** (`queries.py:326`).
  - Fix: treat them as invalid, and purge the link rows along with the request.
- **L5. No `Cache-Control: no-store`** on the reveal, phone-check, detail and secure pages.
- **L6. Someone can lock another person's address out of intake for a day** with wrong codes.
  - Fix: count failures per draft plus IP.
- **L7. Policy:** an Administrator impersonating a Director can reveal requester details, even though Q-124 says "masked, no reveal".
  - Fix: block it, or accept it and log a Q (Q-151).
- **L8. Audit and retention details:**
  - the regeneration audit lacks the verification method;
  - the 7-year purge keeps free text and `value_key` (Q-145);
  - the resend `assert` gives a 500.

## Checked and OK
- Every public route is scoped by the token or the draft cookie.
- Media commands are OWN_REQUEST scoped (no IDOR).
- Confirm links are scanner-safe: GET shows a page, POST consumes.
- CSRF protection is on everywhere, including `upload.ts`.
- Tokens are HMAC-hashed, with an encrypted copy, and superseded tokens are revoked.
- The draft cookie is signed, httponly, Secure and Lax.
- Subjects, titles and payloads are PII-free.
- Code emails are encrypted in job args.
- The Administrator sees details masked.
- The phone check is blocked while impersonating.
- Reveal audits carry field names only.
- `Referrer-Policy: same-origin` is set.
- The service worker doesn't cache pages.

## Re-check at `255a586` (after FIX-A/B/C)

The two original proof-of-concept exploits no longer work. The verify-swap now returns 422 and creates no request. "Find my request" enumeration now gives identical output whether or not a request exists.

| ID | Status |
|---|---|
| H1–H4 | Fixed |
| M1–M4 | Fixed |
| M6 | Fixed |
| L1–L5 | Fixed |
| M5 | Partly fixed; the worker config is covered by new finding N2 |
| L7 | Partly fixed; covered by new finding N5 |
| L8 | Partly fixed; the regeneration method is still missing |
| L6 | Not fixed; its intent was defeated (new finding N3) |

New findings, all addressed in FIX-E:
- **N1 (Medium):** the leader media routes skip record scope.
- **N2 (Medium):** the worker service is missing the env vars that `prod.py` now requires.
- **N3 (Medium):** `verify_code` picks the challenge by email only.
- **N4 (Low):** `value_key` is erased through `.update()`.
- **N5 (Low):** Q-151 isn't applied to the gallery.
- **N6 (Low):** media purge hook edge cases.
- **N7 (Low):** `notification_open` issues on GET.

## Final re-check at `f1d4fb9`

All earlier proofs of concept were re-run and none reproduce.

| Item | Status |
|---|---|
| L6, N1–N7, L8 | Fixed |
| N7 | Small leftover accepted: a GET marks your own notification read when not impersonating |

New findings, fixed in FIX-G:
- **NH1 (High):** the "already received" screen showed the HAM # and the live secure-page token to any browser whose session held a used draft, without a code.
- **NM1 (Medium):** anyone could trigger find-my-request, which revoked the requester's working link and could flood their inbox. It overlaps PRD NEW-2.
- **Lows:**
  - a find-path timing difference;
  - the intake cooldown is keyed by email only;
  - one flaky test file.
