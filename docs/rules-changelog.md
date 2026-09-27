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
