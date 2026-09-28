# Step 2 (Intake): PRD conformance review (ham-prd-guardian)

Scope: `git diff main...HEAD` on `feature/step-2-intake` at `fd5228f`. The reviewer had no write tool; the orchestrator saved this report verbatim in substance.

**Result:** not ready to merge: **1 Blocker, 9 Majors**, several Minors. Scope is clean: nothing from step 3 was built (approvals, rejection, HAM questions, urgent certification), and nothing deferred either (Drive, SMS, background checks, multilingual).

## Conforms
- **Public form:** §6, §6.1 (with Q-025 for email), §6.2, §4.1, plus Q-105 relationships and the tenant/HOA lines. No membership question (§77 step 1).
- **Verification:** verify before submit (Q-100); the no-email path is held for a Director/AD phone check (Q-025), audited and blocked while impersonating.
- **Links:** §7.2, §7.3, §60.3, §76. The old link is revoked when a new one is issued, and lifetimes come from `ham/rules`.
- **Duplicates:** §9, §76. Keyed matches only, handled by a background job, and never a rejection.
- **Urgent requests (§10, §35):** Q-123 and Q-133 recipients. Certifying urgency is correctly left to step 3.
- **Media:** §45 and §46 limits come from the rules module, and originals are deleted after processing.
- **Notifications:** subjects are neutral and leadership emails carry HAM # and category only (§35, Q-102, Q-122).
- **Privacy:** reveals are logged (Q-024), the Administrator sees masked details (Q-124) and photo counts only (Q-138).
- **Pre-decision close:** only the Q-107 reasons plus Q-140 are offered.
- **Rules module:** all intake values are versioned there. Retention follows Q-127.
- **Bottom-nav Requests item:** conforms.

## Blocker
- **B1. The stored certification is not what the requester ticked** (§6.2, Q-103).
  - Three wordings exist: `r6_review.html:67-95`, `ham/requester_portal/attestation.py:42-59` and `ham/requests/certifications.py:23-34`.
  - `requester_portal/services.py:338` replaces the ticked codes with `required_statements()`, and `requests/services.py:175` stores `intake-v1`.
  - **Fix:** one module for wording, codes and version, used both to render and to store; store the ticked codes. Add a test that the stored text equals the rendered text.

## Majors
- **M1. Category and home type are rewritten on submit, and some answers are lost** (Q-109, Q-110).
  - Where: the translation tables at `requester_portal/services.py:297-315, 350-357` map onto the older lists in `requests/models.py:30-54`.
  - **Fix:** one vocabulary and no translation. Check that `max_length` fits the codes.
- **M2. The Administrator sees the duplicate alert** (§9).
  - Where: `views_requests.py:178, 211-223`, `_request_detail.html:53`, `requests_list.html:63-65`.
  - **Fix:** gate both on `request.history.view`.
- **M3. Leaders can't view photos or videos** (§45, §46, §69, §77 step 3).
  - Where: there are no `/requests/<uuid>/media/<mid>/(thumb|view)` routes, and the detail page shows text only.
  - **Fix:** add the routes and a gallery. The Administrator keeps the count only (Q-138).
- **M4. Link regeneration doesn't record the verification method** (§7.3, §58).
  - Where: `requester_portal/services.py:205-221`. The challenge row it points at is erased after 7 days.
  - **Fix:** record the method in the audit and write a `RequestContactVerification` row with purpose `link_regeneration`.
- **M5. Visit availability isn't required** (Q-099, decided).
  - Where: `requester_portal/forms.py:168-179`.
  - **Fix:** require at least one chip; "Any time works" counts.
- **M6. The R5 "Anything else about reaching you" note is collected, then dropped** (Q-105, Q-148).
  - **Fix:** store it and show it on L2 and L9, or remove the field.
- **M7. A requester could open a new photo batch on their own** once a batch closes (§46).
  - Where: `media/services.py:121-143`.
  - **Fix:** only ever auto-create batch #1.
- **M8. The close note can end up in the URL, and so in server logs** (§68).
  - Where: `views_requests.py:347-349` and the duplicate prefill link.
  - **Fix:** re-render the form on error; prefill by request id, never by text.
- **M9. Church-issued codes are captured, then dropped**, with a bare `PRD-GAP:` marker (§6, Q-114).
  - Where: `requester_portal/services.py:373-377`.
  - **Fix:** wire the code, or remove the capture and record the deferral on Q-114. Either way, use the marker `PRD-GAP Q-114`.

## Minors
- **N1.** Wrong Q references:
  - `requests/certifications.py:5,13` cites Q-102; it should be Q-103.
  - `requests/models.py:31` cites Q-107; it should be Q-109.
  - `requests/models.py:58` cites Q-124; it should be Q-111. Also drop `TEXT_MESSAGE`, which Q-111 doesn't offer.
- **N2.** The unused `request.create_assisted` action gives Pastors a staff-entry power. Remove it.
- **N3.** The new-link email always says 14 days, which isn't always the link's real lifetime (Q-149).
- **N4.** The secure page greets by full name; it should use the first name.
- **N5.** Wrong reason key in `projection.py:30`: `couldnt_reach` should be `couldnt_reach_them`.
- **N6.** Media audit events lack the request id in `project_id`, so the §58 project filter misses them.
- **N7.** The intake verification method is always recorded as `email_code`, even when the emailed link was used.
- **N8.** The history timeline shows no actor on a close, and the "Awaiting Approval" entry disappears after cancellation.
- **N9.** The photo-count-only rule applies to anyone with the Administrator role, even if they also hold a leadership role. Use `is_masked_view(ctx)`.
- **N10.** `reopen_batch` doesn't refuse a closed request or a no-email request.
- **N11.** The secure page ignores the batch state and the leader's reason for more photos.
- **N12.** The R6 privacy line has no privacy-statement link (Q-131).
- **N13.** Wrong-code lockouts aren't audited.
- **N14.** The "24 hours" in the code-limit message is hard-coded; it should come from the rules module.
- **N15.** State is a required free-text field with no prefill (Q-147).
- **N16.** "Change category" isn't built. Defer, and add a note on Q-109.
- **N17.** The in-app "new photos arrived" notice isn't built. Defer (Q-150).

## New PRD gaps
Q-144 to Q-150 have been logged in `docs/prd-open-questions.md`.

## Acceptance progress (§77)
| Step | Status |
|---|---|
| 1 | Met |
| 2 | Met |
| 3 | Partly met (B1, M1, M3) |
| 28 | Helped (M4, N6 open) |
| 30 | Helped (M2, M8 open) |
