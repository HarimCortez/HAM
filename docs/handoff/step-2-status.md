# Step 2 (Intake): handoff status

Branch: `feature/step-2-intake`. **Step 2 is complete** (all waves, test pass, four reviews and fix rounds); PR opened to `main`. The notes below describe the state before wave 3 and are kept for history.

Follow-ups left (Low/Minor): security N-L1–N-L3 + find-path timing (see `docs/ux/reviews/step2-privacy-security.md`); "Change category" (step 3, Q-109); Q-150 new-photos notice; Q-114 manage screen; privacy-statement link (Q-131, waiting on owner text); visual/wording minors at the end of each `docs/ux/reviews/step2-*.md`.

Waves 1 and 2 are merged. The suite is green: 2010 passed, 34 skipped, and ruff, mypy, lint-imports, makemigrations --check, build_permission_matrix --check and build_tokens --check all pass.

## Read first
- The owner decisions box at the top of `docs/architecture/intake.md`. The body is the architect's plan, and the box overrides it.
- `docs/architecture/intake-contracts.md`, the exact cross-slice contracts:
  - S2.0 seams;
  - §8 S2.3 portal;
  - the S2.2 notes in the module docstrings.
- `docs/ux/intake.md`, the final UX spec (R1–R12, L1–L11). `design-system/screens/intake.md` has the hi-fi specs; the components are in `design-system/components.md` C§19–§32.
- `docs/prd-open-questions.md`: Q-025 and Q-099–Q-143. Decided rows are final. The rest run on proposed defaults.
- `.claude/agent-memory/*/`, the conventions of every agent.

## Owner decisions (step 2)
| Q | Decision |
|---|---|
| Q-100 | Verify before submit |
| Q-025 | Email, or "I don't use email". Requests without email are held in "Needs a phone check" until a Director or AD verifies them by phone. This departs from PRD §6.1, and the owner accepts that. |
| Q-127 | Keep for 7 years after close, then erase name, email, phone and street. Spam is erased after 90 days, and unfinished forms after 24 hours. |
| Q-124 | The Administrator can view requests, with contact details masked and no reveal |

## Done
| Slice | What |
|---|---|
| S2.0 | Authz contexts and actions, platform otp/net/storage, empty apps, oracle |
| S2.1 | Rules 2026.09.28-4, states.py, matching.py, validity.py |
| S2.2 | Requests core: models, submit_request, duplicate check, verify_by_phone, cancel (Q-107 plus Q-140 "couldn't reach them"), reveal (Q-024), Administrator masking, attention providers, retention sweep, seed_dev_requests |
| S2.3 | Requester portal backend: encrypted drafts, resume cookie, form validation, verification code and link, issue/resolve/regenerate/find links, anti-abuse, projection, purge jobs; ChurchProfile.serves_days |
| S2.4 | Object storage (R2 and local) plus the media domain: batches, processing, EXIF/GPS strip, originals deleted, retention. Rules 2026.09.28-5. ffmpeg isn't installed in the sandbox, so video processing degrades to "processing_unavailable". |
| S2.5 | In-app notifications, the attention registry, Inbox queries, urgent banner, notification_recipients |

## Known loose ends (do these first)
1. **S2.2 did not register the three portal lookups.** `RequestsConfig.ready()` must call:
   - `ham.requester_portal.services.register_request_facts_lookup`
   - `register_request_contact_lookup`
   - `register_email_to_request_ids_lookup`

   Without them, `issue_link` / `resolve_token` / `regenerate_link` / `find_my_request` raise RuntimeError at runtime. Also check the S2.3 `submit_and_issue_link` orchestration end to end: it builds `SubmittedRequestPayload` from the decrypted draft, then calls `submit_request` and then `issue_link` in one transaction, and records `requester_link.issued`. Remove the `# type: ignore[arg-type]` for `verification_id=None`, since it is now Optional. Add an integration test covering draft → code → submit → link → resolve.
2. Confirm that `ham/media/subscribers.py` (the RequestCancelled handler) matches S2.2's cancel event (event type plus `aggregate_type="request"`).
3. S2.4 flagged these; confirm or leave:
   - the initial batch open is not audited (only the reopen is);
   - the new failure code `processing_unavailable`.
4. One pytest warning is still outstanding. Worth a look.

## Remaining (wave 3, then close-out)
Run the slices in parallel worktrees with the common brief below. Each slice gets its own DB; merge after each.

| Slice | Owner | What |
|---|---|---|
| S2.6 | integrations engineer | Notification builders: requester emails (neutral subjects, link in every email per Q-102); leadership email and in-app via `register_inapp`; urgent overrides the preference (Q-123/Q-133); a PII-free subject test |
| S2.7 | frontend engineer | Public screens R1–R12 at 390/768/1280 plus 200% text: the form wizard, "I don't use email" path, verify, R7/R7N, secure page, TypeScript upload module (presigned PUT, progress, retry), expired/new-link/find pages. The emailed link paths `/request-help/verify/link/<token>` and `/request-help/new-link/<token>` must exist as literally named. Add the `serves_days` control to Church settings. |
| S2.8 | frontend engineer | Leadership screens L1–L11: Requests list (HAM # plus category only), split detail at ≥1280, "Show contact details" reveal, Needs-phone-check list plus the L9 verify sheet, L10 close sheet, L11 ask-for-more-photos, the duplicate panel, Home attention cards, Inbox, urgent banner; flip the `requests` nav item to built |
| S2.9 / S2.10 | — | Phone check (covered by S2.2 services plus the S2.8 UI). Jobs are mostly done; verify every periodic job is registered. |

Then:
1. ham-test-engineer: fill the §9-style gaps, e2e for PRD §77 steps 1–3, and update the oracle.
2. The four reviews in parallel (privacy-security, prd-guardian, UX usability, UI visual QA with screenshots).
3. Fix every Critical/High finding and re-verify.
4. Open the PR to `main`, following the step-1 PR format (#2).

The owner asked for the PR when step 2 is done.

Common brief for slice agents: `docs/handoff/wave-brief.md`.
