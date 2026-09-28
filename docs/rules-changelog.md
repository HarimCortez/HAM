# HAM rules changelog

The rules module (`ham/rules/`) holds every fixed business number: staffing timelines, reliability weights, retention periods, link lifetimes, upload limits, and sign-in and session limits. These are fixed system rules, not Administrator settings (PRD §34, §76). The Admin "Rules" screen shows them read-only.

## How to change a rule
1. Change the value in `ham/rules/v1.py`. Keep its PRD § and Q-id in `sources`.
2. Bump `RULES_VERSION` (`YYYY.MM.DD-N`).
3. Add a section below: what changed (old → new), why, and who decided (Q-id).
4. Add the new version and hash to `PINNED_HASHES` in `tests/rules/test_rules_version_hash.py`. Don't edit old lines.

The version/hash test fails if a value changes without steps 2–4. Changing labels, notes, or sources does not change the hash and needs no bump.

Every audit event and reliability score change stores the `RULES_VERSION` that applied, so past decisions can be explained with the rules in force at the time (PRD §34, §58).

`Pending` values are open PRD questions. Any code that tries to use one raises `RuleNotDecidedError`. Deciding one is a value change, so it needs a version bump.

---

## 2026.09.27-1 — initial rule set

Content hash: `sha256:e13eb47656eceb028c495b3f5e918fb4274d9fdc7b752fce3ba1b434ee77188a`

Initial values from the PRD and the owner decisions dated 2026-09-27 in `docs/prd-open-questions.md`:

- **Staffing:** 48 h invitation response (Q-002); 24 h waitlist confirmation (§29, §32); automatic staffing stops 48 h before start (§29, §30); understaffed alert at 96 h (Q-013); reconfirmation at 7 days, with daily reminders on days 7, 6 and 5 (Q-011); unconfirmed slots released at 5 days (§32); 48 h leader alert for an unaccepted changed agreement (Q-014).
- **Reliability:** score from 0 to 100, starting at 100 (§34, §34.1). Cancellation bands are 7+, 4–6, 2–3, 1 and 0 days. No penalty for cancelling 7 or more days out, for excused events (§33, Q-022), for deactivation or account-turn-off cancellations (§21, Q-052), or for declining a last-minute assignment (§30). The penalty numbers and the recovery rate are **Pending (Q-001)**.
- **Credentials:** expiry alerts at 60, 30 and 7 days (§24.1).
- **Attendance:** 15-minute late grace period (Q-020). The leader's phone is visible from the day before the project (church-local days; Q-023, Q-030).
- **Requester and survey:** the requester link stays valid 7 days after completion; a regenerated link lasts 14 days (§7.3). The survey link lasts 30 days, with one reminder at 7 days, and the rating scale is 1–5 (§54).
- **Media:** each batch allows 10 photos and 3 videos of up to 2 minutes each (§45, §46). Videos are kept 30 days and photos 90 days after Completed or Rejected (§47).
- **Retention:** audit events 1 calendar year (§58, Q-036). Incidents, homeowner agreements, and volunteer agreements (after the volunteer becomes inactive) 7 calendar years (§41, §42, §56). Years are counted on the calendar, so a leap year never makes a purge happen early.
- **Sign-in and security:**
  - Two-step sign-in is required for Administrator, HAM Director, Assistant Director, Pastor, and Board representative (§60.1, Q-045).
  - A trusted device lasts 30 days (Q-010). Users get 10 recovery codes (Q-035).
  - Step-up is required for role grant/revoke, audit export, MFA reset, starting impersonation, regenerating recovery codes, and changing the sign-in email. One step-up covers 5 minutes per action kind (Q-046).
  - The emailed code has 6 digits, lasts 15 minutes, and allows 5 tries (Q-032).
  - Sessions: 30 days idle for roles without two-step sign-in. Two-step sign-in roles get 8 h idle and 7 days absolute (Q-032).
  - Impersonation idles out after 15 minutes (§59).
  - **Pending:** sign-in email rate limit and resend cooldown (Q-070), account invitation lifetime (Q-071), authenticator-code attempt limit (Q-072).
- **Reporting:** the public-embed small-group threshold is **Pending (Q-027)**.
- **Integrations (engineering):** outbox retries 8 attempts, backing off from 1 minute up to a 6-hour cap (§70.3, foundation.md §5).

## 2026.09.28-1 — proposed defaults in use for open questions

Content hash: `sha256:84f96591b6cae641b20e83cc70ea0eff466990850f31c207d6f0249ccd3983d7`

On 2026-09-28 the product owner decided to run on the **proposed defaults** of Q-001, Q-056, Q-070, Q-071, Q-072, Q-073, Q-074, Q-075, Q-076 and Q-077 for now. These questions stay "Open" in `docs/prd-open-questions.md`, so the owner may still change them. Each affected rule lists its Q-id in `provisional`, and its note says "PRD-GAP Q-NNN: proposed default in use; owner may change". The Admin "Rules" screen labels it "Proposed default — may change".

Value changes (Pending → value):

- **Reliability (Q-001):** cancelling 4–6 days before costs 3 points (small), 2–3 days 6 (moderate), 1 day 10 (larger), and same day 16 (major). A no-show costs 20 (largest). Each commitment fulfilled as committed recovers 2 points. The score stays within 0–100. Rationale: the penalty roughly doubles as the project day gets closer, because a later cancellation leaves less time to find a replacement. Same-day is "substantial but slightly less than a no-show" (§33). Earning back one no-show takes 10 fulfilled commitments.
- **Sign-in (Q-070):** at most 5 sign-in emails per address in any rolling hour, and a 30-second wait before "Resend email".
- **Account invitation (Q-071):** 7 days. This value is declared only. Invitations currently reuse ordinary sign-in (Q-084), so no code enforces it yet.
- **Two-step sign-in (Q-072):** after 5 wrong authenticator or recovery codes, the person has to start again from a new email sign-in.

New rule:

- **Operations (Q-056):** new group `operations` with `HEALTH_MAX_QUEUE_LAG` = 5 minutes. `GET /healthz` reports "degraded" once the oldest due background job has waited longer than that. This replaces the literal `MAX_HEALTHY_QUEUE_LAG_SECONDS = 300` in `ham/web/views.py`.

Metadata only (no value change). These are now marked as proposed defaults in use:

- **Q-073:** "N days before the project" means calendar days in the church time zone. Reminders go out at 09:00 local, and the release happens at the end of day 5. Hour-based rules use elapsed time. This covers the reconfirmation, reminder, release and cancellation-band day rules.
- **Q-074:** incident retention counts from the last amendment. Homeowner-agreement retention counts from signing or project close, whichever is later.
- **Q-075:** cancelling on the project day after the start time counts as a no-show unless excused.
- **Q-076:** role grant and role revoke share one step-up kind ("role changes"), so one 5-minute step-up covers both.
- **Q-077:** V1 has no reliability penalty for an unanswered invitation, an unconfirmed waitlist promotion, or a slot released because the volunteer did not reconfirm. This is deliberate, so no rule value exists for these.

New invariants:
- The resend cooldown is positive and under an hour.
- The sign-in email limit and the authenticator attempt limit are each at least 1.
- An invitation lasts longer than a sign-in code.
- The health lag threshold is positive.
- The Q-001 ladder is now always checked (`check_reliability_penalties`).

Still **Pending:** the public-embed small-group threshold (Q-027).

## 2026.09.28-2

Content hash: `sha256:870301de1d7d500763632d339a9bc9cf0eeabf7c8b117d32466bb2e17f3de9da`

Security review follow-up (H1/M2/M3/Q-070): two new `auth` rules, both proposed defaults for
the still-open Q-070 (sign-in email rate limit and resend cooldown):

- **`SIGN_IN_REQUESTS_PER_IP_PER_HOUR`** = 20: a per-address limit alone doesn't stop one
  visitor from cycling through many email addresses; `ham.identity.authn.request_sign_in` now
  also throttles by requesting IP.
- **`SIGN_IN_FAILED_ATTEMPTS_PER_ADDRESS_PER_DAY`** = 20: a fresh sign-in email resets the
  per-challenge 5-wrong-code limit, so without a daily cap per address an attacker could keep
  requesting new codes to keep guessing. This is a rolling-24-hour cap across all challenges
  for one address.

New invariant: both new rules must be at least 1.

- **`SIGN_IN_CHALLENGE_RETENTION`** = 7 days (security review L5): a background job purges
  `identity_sign_in_challenge` rows older than this — they exist only to rate-limit/lock out
  by address, not as a record worth keeping.

## 2026.09.28-3

Content hash: `sha256:2635dba3e86d2066f3a3069d9191682b4c293e3702b3dccefa6b71dc67ea011e`

Security round-3 re-review (N9, M9): two new rules —

- **`outbox.JOB_PAYLOAD_ENCRYPTION_TTL`** = 1 day: `ham.integrations.email.service`'s
  encrypted background-job payload (security review C2) is now also time-bounded via Fernet's
  built-in TTL, not just key-rotatable — a captured/exfiltrated old `procrastinate_jobs` row
  can't be decrypted forever with a leaked `HAM_FIELD_ENCRYPTION_KEY`.
- **`operations.RECENT_ACTIVITY_WINDOW`** = 24 hours: replaces a bare `timedelta(hours=24)`
  literal in `ham.web.views._recent_sign_in_failures` (the Administrator Home "recent sign-in
  failures" summary).

## 2026.09.28-4 — step 2 (Intake)

Content hash: `sha256:77c70f3c4751ab55b2fb106b369f6f34bb6e74bc5ed41374de8cc06aad4d4068`

New group `intake` ("Public request form and requester codes") and new rules in
`requester_access`, `media` and `retention`. Decided values are plain; the rest are proposed
defaults in use (`provisional`, "PRD-GAP Q-NNN: proposed default in use; owner may change").

Decided (owner, 2026-09-28):
- **Q-127 retention:** `retention.REQUEST_RECORD_RETENTION_AFTER_CLOSE` = 7 calendar years,
  then name, email, phone and street are erased (ZIP, category, outcome kept);
  `retention.SPAM_REQUEST_RETENTION` = 90 days after a spam/test close;
  `intake.INTAKE_DRAFT_LIFETIME` = 24 hours for unfinished (unverified) forms.
- **Q-100 requester code:** `intake.REQUESTER_CODE_LENGTH` = 6 digits,
  `intake.REQUESTER_CODE_LIFETIME` = 15 minutes (as sign-in, Q-032).

Proposed defaults in use:
- **Q-116:** `requester_access.REQUESTER_ACCESS_AFTER_CLOSE` = 7 days: normal link access
  for a request closed without completing (Cancelled, Not Executable, final Rejected).
- **Q-117:** `requester_access.EARLY_REGENERATED_LINK_FOLLOWS_NORMAL_ACCESS` = Yes: a link
  regenerated before normal access ends lasts as long as the normal link; the 14-day
  lifetime applies only to links regenerated after normal access ended.
- **Q-121 abuse limits:** 10 forms per IP per rolling hour; 3 submitted requests per email
  per rolling 24 h; 20 "find my request" tries per IP per rolling hour; minimum fill time
  3 seconds (Q-121 names the check without a number; 3 s is from the architecture plan §9).
  Requester code limits "as sign-in": 5 wrong tries per code, 5 code emails per address per
  hour, 30 s resend cooldown, 20 wrong codes per address per 24 h, records erased after
  7 days. Separate names from `auth.*` so staff sign-in and requester codes can diverge
  later; a test pins them equal today.
- **Q-119 uploads:** photos ≤ 25 MB (JPEG, PNG, HEIC/HEIF, WebP), videos ≤ 500 MB (MP4,
  MOV); MB = 1,048,576 bytes (the generous reading). Stored as bytes and MIME types.
- **Q-128:** `media.MEDIA_RETENTION_CLOCK_ON_CANCELLATION` = Yes: media on Cancelled
  requests/projects follows the §47 photo (90 d) / video (30 d) clock from cancellation.
  New pure helper `media_retention_period(kind, closing_status)`; statuses without a rule
  (e.g. Not Executable) raise instead of guessing.

Not added (deliberately):
- **Q-112** "days HAM serves" is a church-profile setting (default Sunday–Friday), not a fixed
  business rule, so it does not belong here.
- **PRD §5** "no fixed limit": there is no per-household or per-address request limit.

New invariants: access after close positive; draft lifetime > requester code lifetime;
requester resend cooldown in (0, 1 h); minimum fill time positive and < draft lifetime;
intake limits ≥ 1; daily wrong-code cap ≥ per-code tries; challenge retention > 24 h; upload
sizes positive, photo ≤ video; media type lists non-empty, unique, lower-case, right family;
spam retention positive; request retention ≥ 1 year.

## 2026.09.28-5 — step 2 (S2.4a/b: object storage, media)

Content hash: `sha256:66abce06bc3b003b2ec564dc7a763c7a3d062afb4a7a0a017349b60c31f20ce3`

Three new engineering values in `media`, all named in intake.md §9's rules table but not
previously in the rules module:
- `media.MEDIA_UPLOAD_INTENT_LIFETIME` = 1 hour: an unconfirmed upload reservation (a slot
  held but never completed) is released after this long, freeing the slot.
- `media.PRESIGNED_UPLOAD_URL_LIFETIME` = 15 minutes: how long a presigned PUT URL handed to
  a requester's browser stays valid.
- `media.PRESIGNED_VIEW_URL_LIFETIME` = 60 seconds: how long a presigned GET URL for a
  thumbnail/photo/video stays valid.

These are engineering values (intake.md §9), not Q-numbered open product questions, so they
carry no `provisional=` tag.

New invariant: the presigned upload URL must not outlive the reservation it belongs to
(`PRESIGNED_UPLOAD_URL_LIFETIME <= MEDIA_UPLOAD_INTENT_LIFETIME`); the view URL lifetime must
be positive.

## 2026.09.28-6 — step 2 fix round (FIX-B: media security)

Content hash: `sha256:da176a0734d061ccc65edf97000c4cf458fe4c76b4d4c0f8de241d6c22d455e5`

One new engineering value, `media.MEDIA_PROCESSING_TIMEOUT` = 1 hour: an item stuck in
`processing` (the worker died mid-job, e.g. an OOM'd ffmpeg re-encode) is treated as failed
and its slot freed after this long, found by the security review's M3 ("reserved slots never
free up"). Not a Q-numbered open question -- same engineering-value category as the other
`media.*` lifetimes above.

New invariant: the processing timeout must be positive.
