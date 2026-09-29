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

## 2026.09.28-4 — step 2 intake (S2.1, branch s21)
Q-numbers: use docs/prd-open-questions.md Q-099–Q-132 (intake.md body numbers are stale drafts).
- New group `intake` (label "Public request form and requester codes"). Requester codes have
  their OWN names (REQUESTER_CODE_*, REQUESTER_CHALLENGE_RETENTION) with sign-in values;
  `test_requester_codes_match_sign_in_values` pins them equal. Decided: length 6, lifetime
  15 min (Q-100/Q-032), INTAKE_DRAFT_LIFETIME 24 h (Q-127). Provisional Q-121: 5 tries,
  5 emails/addr/h, 30 s cooldown, 20 wrong/addr/24 h, retention 7 d, 10 forms/IP/h,
  3 submissions/email/24 h, 20 find-my-request/IP/h, min fill time 3 s (number from plan §9).
- requester_access: REQUESTER_ACCESS_AFTER_CLOSE 7 d (Q-116); bool
  EARLY_REGENERATED_LINK_FOLLOWS_NORMAL_ACCESS True (Q-117). Bool rules are allowed now; the
  values test keeps an explicit BOOL_RULES set.
- media: REQUESTER_PHOTO/VIDEO_MAX_BYTES 25/500 MiB (binary = generous reading), *_TYPES as
  lower-case MIME tuples (HEIF with HEIC) (Q-119); MEDIA_RETENTION_CLOCK_ON_CANCELLATION
  True (Q-128). Helper `media_retention_period(kind, closing_status)` raises for statuses
  without a rule (NOT_EXECUTABLE: open gap, never guess). view.py formats *_BYTES as "N MB"
  and *_TYPES via MEDIA_TYPE_LABELS.
- retention (decided Q-127): REQUEST_RECORD_RETENTION_AFTER_CLOSE CalendarYears(7) (then
  erase name/email/phone/street), SPAM_REQUEST_RETENTION 90 d.
- NOT rules: Q-112 days HAM serves (church profile setting); PRD §5 no per-household limit
  (test forbids such a rule name).
- `ham/requests/states.py`: NEEDS_PHONE_CHECK is a STATE (Q-025), entered by
  SUBMIT_WITHOUT_EMAIL, left only by VERIFY_BY_PHONE (DIR/AD, IB) -> SUBMITTED, or CANCEL.
  CANCEL reasons exactly spam / requester_withdrew / duplicate_submission (Q-107; no
  "other"); no requester email for spam. TERMINAL = {CANCELLED} in step 2; "closed" is
  `closed_at`, not status (reconsiderable REJECTED is open). VERIFY_BY_PHONE has no outbox
  event (audit request.contact_verified). check_transition returns Refusal codes, never raises.
- `ham/requests/matching.py`: keys address(+unit)|ZIP5, E.164 phone (is_valid_number, else
  None), email (lower; Gmail dots/+tag only), sorted-name-words|ZIP5 (drops initials,
  titles, Jr/Sr/III; >= 2 words). Unit designators APT/UNIT/STE/#/LOT/SPACE/TRLR/RM/PH/NO
  collapse to "#"; BLDG/FL kept. MATCH_KEY_VERSION=1 -> bump when normalization changes.
- `ham/requester_portal/validity.py`: valid while now < valid_until; regenerated at exactly
  the access end counts as "after" (14 d). completed_at beats closed_at. Naive datetimes and
  inconsistent status/timestamps raise ValueError. NEEDS_PHONE_CHECK -> NO_ACCESS.

## 2026.09.28-9 — step 3 approvals (S3.1, branch s31-rules)
Q-numbers: docs/prd-open-questions.md Q-153–Q-176; the owner box at the top of
docs/architecture/approvals.md overrides its body (30 d window and "no undo" are superseded).
- New group `approvals`: RECONSIDERATION_REQUEST_WINDOW = 14 as an **int of church-local
  calendar days** (unit "days"), NOT a timedelta, so `decided_at + window` can't silently give
  an elapsed-time cutoff. Provisional Q-174 (the reading); value decided Q-155.
  DECISION_UNDO_WINDOW = timedelta(30 min), decided Q-156, not provisional.
  Invariant: 0 < undo < 1 day <= window days; window int >= 1 (bool rejected).
  Metadata only: REQUESTER_ACCESS_AFTER_CLOSE and PHOTO/VIDEO_RETENTION cite Q-155.
- Date math (states.py): `reconsideration_last_day` = church-local date of decided_at + 14
  days; `reconsideration_deadline` = datetime.combine(last_day, time.max, tzinfo=zone) -> UTC
  (23:59:59.999999). Tested DST both ways in America/New_York, fold=1 hour, year end.
  `may_request_reconsideration`: now <= deadline (inclusive). FINALIZE allowed iff not.
  Undo: `decision_is_undoable` = undone_at is None and now < decided_at + 30 min (at exactly
  30:00 too late; held effects release).
- states.py step 3: actions APPROVE, REJECT, REQUEST_RECONSIDERATION (REQUESTER; DIR/AD by
  phone), RECONSIDER_APPROVE/REJECT, FINALIZE_REJECTION (SYSTEM, self-edge REJECTED ->
  REJECTED, closes), CANCEL + APPROVED/RECONSIDERATION_PENDING (requester_withdrew only).
  `Transition.closes_request` field: CANCEL, RECONSIDER_REJECT, FINALIZE. TERMINAL_STATUSES
  stays {CANCELLED} (validity.py relies on it); use `is_closed(status, closed_at)` (raises
  on a NEVER_CLOSED status with closed_at; unknown later statuses follow closed_at).
  Generic guard: any existing request with closed_at -> ALREADY_FINAL (idempotent finalize).
- Route (Q-164): required each time, must hold ROUTE_ROLE[route]; reconsideration uses the
  RECORDED route. `may_decide_reconsideration`: Board route any BRD; pastoral = original, or
  take_over + unavailable tick; original not an active pastor -> any pastor, no tick, still
  took_over_from. Tick without take_over is NOT a take-over.
- APPROVE/RECONSIDER_APPROVE require the `urgency` fact (FACTS_MISSING) so an urgent approval
  is never missed; `certify_urgent` = pastoral route + certifiable urgency. Decision carries
  `urgent_approval`, `took_over_from`. `becomes_urgent_approval(before, after)` = alert once.
- Urgency sub-machine: CERTIFY from awaiting/not_certified while AWAITING_APPROVAL/APPROVED;
  DECLINE from awaiting only while AWAITING_APPROVAL (arch table; decline-after-Board-approval
  flagged as a new gap). PASTOR only; NONE never certifiable.
- Undo = `check_undo(decision, actor_id, decided_by_id, decided_at, now, undone_at,
  current_status, current_urgency, prior_urgency)`: undoable APPROVE/REJECT/RECONSIDER_*/
  CERTIFY/DECLINE (decline included = my reading of Q-176, flagged). Only decider, not
  impersonating, state must still be what the decision produced. prior_urgency required for
  urgency reviews and for "Approve as urgent". Returns restore_status/urgency,
  reopens_request (RECONSIDER_REJECT), clears_reconsideration_deadline (REJECT),
  urgent_approval_undone (Q-176 follow-up). No audit/outbox names chosen (S3.0 owns).
- `decision_undo_open` fact refuses REQUEST_RECONSIDERATION, FINALIZE and post-decision CANCEL
  (derived from Q-176 "held effects"; flagged).
- RejectionReason StrEnum lives in states.py; a skip-until-present test pins models' choices.
