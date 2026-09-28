# ham-rules-engineer — rule decisions

## Rules module mechanics (`ham/rules/`)
- `RULES_VERSION` `YYYY.MM.DD-N`; content hash covers values only (not label/note/sources/provisional).
  Value change => bump version + `docs/rules-changelog.md` section + append to `PINNED_HASHES`
  in `tests/rules/test_rules_version_hash.py` + update `tests/rules/test_rules_values.py` oracle.
- `Pending(...)` = undecided; raises `RuleNotDecidedError` on any use.
- `provisional=("Q-NNN",)` metadata (added 2026-09-28) = open question running on its proposed
  default. Note must contain "PRD-GAP Q-NNN: proposed default in use; owner may change" (use
  `proposed(q, detail)` helper). Admin Rules screen shows "Proposed default — may change (Q-…)".
  Owner confirms unchanged => drop from `provisional` (no bump). Owner changes value => bump.
- Tests enforce: exact set of Pending rules, exact set of provisional rules, Q-ids in sources.

## 2026.09.28-1 (owner, 2026-09-28: use proposed defaults, questions stay Open)
- Q-001: penalties 4–6d 3, 2–3d 6, 1d 10, same-day 16, no-show 20; recovery +2 per fulfilled
  commitment; clamp 0–100. Rationale: ~doubling toward project day; same-day slightly < no-show
  (§33); a no-show takes 10 fulfilled commitments to recover.
- Q-070: 5 sign-in emails/address/rolling hour; 30 s resend cooldown. "Per hour" window is the
  rule's unit (`_SIGN_IN_RATE_WINDOW` in `ham/identity/authn.py`); boundary: first email still
  counts at exactly +1h (created_at >= now-1h), leaves at +1h+1s.
- Q-071: invitation 7 days — declared, NOT enforced (Q-084: invitations reuse ordinary sign-in).
- Q-072: 5 wrong authenticator/recovery codes -> restart from email (web/auth_views.sign_in_mfa).
  Lockout is NOT audited yet although the proposed default says "audited" (open follow-up).
- Q-056: new group `operations.HEALTH_MAX_QUEUE_LAG` = 5 min; /healthz degraded when lag > limit
  (exactly at the limit is still ok).
- Q-073: day rules = church-local calendar days; reminders 09:00 local; release end of day 5.
- Q-074: incident retention from last amendment; homeowner agreement from later of signing/close.
- Q-075: cancel on project day after start = no-show unless excused.
- Q-076: grant+revoke share step-up kind `role_change` (already true in code).
- Q-077: no penalty for unanswered invitation / unconfirmed promotion / release for not
  reconfirming. Deliberately no rule value.
- Still Pending: Q-027 (public embed min group size).

## Literals judged NOT business rules (left in place)
- `ham/identity/totp.py` TOTP_DIGITS=6, PERIOD=30 s, TOLERANCE_STEPS=1 (RFC 6238 protocol).
- Token/secret byte lengths (`token_urlsafe(32)`, `new_secret(20)`, recovery code format).
- UI page sizes: audit list 50 (`ham/audit/queries.py`, `ham/web/views_audit.py`), audit
  recent-on-detail 5 (`ham/authz/audit_access.py`), outbox `recent_failures(20)`.
- `ham/outbox/dispatch.py` `_MAX_ERROR_LENGTH = 2000` (storage truncation).
- Model `max_length`s; `SECURE_HSTS_SECONDS`; `CONN_MAX_AGE`.
