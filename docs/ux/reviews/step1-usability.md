# Step 1 usability review: sign-in, two-step, roles, audit log, impersonation

Reviewer: ham-ux-designer · Branch `feature/step-1-foundation` (HEAD as of 2026-09-28)
Specs: [auth-and-access.md](../auth-and-access.md), [navigation.md](../navigation.md), [personas.md](../personas.md); CLAUDE.md priority 4.
Scope: templates in `ham/web/templates/web/` (incl. `auth/`), `ham/web/auth_views.py`, `views_admin_users.py`, `views_audit.py`, `stepup.py`, `ham/identity/authn.py`, `ham/authz/guard.py`, screenshots in `docs/ux/screenshots/step1-*`.

**Method and limits.** This session had no shell, so I could not run the dev server or Playwright. I walked each journey by reading the view code paths and templates end to end, and used the PNGs for layout. Every finding below is traced to a line of code. Runtime-only items are marked **(verify)**. The `step1-screens` PNGs **predate S3b**: `me-390.png` still says "Sign-in & security settings are coming soon", and user detail has no Reset or Troubleshoot buttons. Re-capture them before visual QA.

Severity: **Critical** means the journey dead-ends, breaks, or risks harm, and blocks the release. **Major** means real friction, a confusing message, or an AA failure with a workaround. **Minor** means polish.

---

## Critical

### C1. Step-up sends people back to POST-only URLs, loses what they typed, and Cancel loops
**Screens:** D "Confirm it's you" → audit export, new recovery codes, role change, invite, impersonation, MFA reset.
**What happens:**
- **Marcus, audit export (journey 2.7):** `audit_export` redirects to `/step-up?next=/audit/export`. After a correct code, `step_up` does `redirect(next)`, which is a GET to a POST-only view. The result is **405** and no file. The filters are lost too. Cancel (`href="{{ next }}"`) goes to the same 405.
- **Any MFA user, Me → Make new recovery codes:** the same thing happens, because `/me/security/recovery-codes` is POST-only.
- **Nadia, role change (2.6), Cancel:** Cancel links to `/admin/users/<id>/roles/resume`. That view re-applies the stashed change, raises `StepUpRequired` again and sends her back to step-up. **Cancel never cancels.** The step-up page uses `base_public` (no nav), so the only way out is the browser Back button or typing a URL.
- **Nadia, impersonation (2.8), MFA reset (2.5), and invite:** after step-up she comes back to an **empty** form (reason, verification method, or name and email) and has to fill it in and submit again.

**Fix:** stash the pending command, as roles already do, and give step-up two explicit URLs: `continue_url`, a GET endpoint that replays the stashed command and then lands on a result page, and `cancel_url`, the originating screen with nothing changed. For export, the continue URL should be a GET `/audit/export/download?token=…` that streams the file and then returns to `/audit?<filters>`. Cancel must drop the stash and return to where the person was: "Nothing changed." Apply the same pattern to invite, impersonation, MFA reset, recovery codes and sign-in email change.

### C2. The Administrator's phone nav hides Audit log and Me, so sign-out is unreachable (Q-091)
**Screen:** bottom nav at 390 (`home-390.png`, `audit-log-390.png`).
**What happens (Nadia, Marcus on a phone):** seven 64px-minimum tabs need 448px. `.nav--bottom` has no overflow handling, so "Rules" is clipped and **Audit log and Me are off-screen**. Me is the only route to Sign-in & security, and there is no account menu anywhere (C5), so **an Administrator on a phone cannot sign out**. The same problem applies to any role whose built item count goes above 5.
**Fix:** do not ship the flat list. Build the navigation.md §3.1 set for the Administrator: **Home · Admin · Inbox · More**.
- **Admin** is a simple index page with Users & roles, Church settings, Integrations, Rules and Audit log. It is a server-rendered list, so no new component is needed.
- **More** holds Me and Sign out.
- Add a rule in `nav_for` that caps the bottom nav at 5 items and pushes the rest into More for every role, so this can't happen again as more screens land.

### C3. Invitations are never emailed (Q-084)
**Screens:** Invite someone → Users & roles.
**What happens (a new volunteer, Samuel given a role):** `invite_user` creates the user and emits `UserCreated` to the outbox, but **nothing consumes it and no email is sent**. The only emails sent in the codebase are the sign-in email and the MFA-reset notice. Meanwhile the invite screen promises "They'll get an email with a sign-in link," and G3 says "{name} gets an email about their new role." That email is not sent either. The invited person never learns they were invited, and Nadia believes they were.
**Fix:**
1. Send an invitation email on invite. Subject: "{inviter} invited you to HAM at {church.shortName}". Body: one line saying who invited them and why, then a sign-in link and code. Reuse the sign-in challenge with the Q-071 lifetime.
2. Send the role email on grant: "You've been added to HAM as {role}". For roles that need two-step sign-in, add "Next time you sign in, we'll help you set up two-step sign-in (about 3 minutes)."
3. Until both exist, change the copy so it doesn't promise an email: "Let them know to sign in at {url} with this email."

### C4. Losing a phone is a dead end: no request to an Administrator and no way to add a new phone
**Screens:** C4/E1 "I can't use my authenticator app" and F Sign-in & security.
**What happens (Marcus, journey 2.5):**
- The recovery view offers only a code field. There is no **Ask an Administrator for help** (E1 option 2), no contact line and no link back to the authenticator.
- Without codes, Marcus has nothing to do on the page.
- With codes, he gets in, but there is **no E2 card** and no **Set up a new phone** anywhere. `mfa_setup` redirects enrolled users away, and `me_security` has no re-enroll action. Every later sign-in burns another recovery code until he runs out.

**Fix:**
- On the recovery screen, add a Link "Back to the authenticator code" and a second option, **Ask an Administrator for help**, which creates an Inbox item for the Administrators. As an interim if that item can't be built yet, show: "No recovery codes? Contact {church.hamEmail} or {church.hamPhone}. An Administrator will check it's you and reset two-step sign-in."
- In F, add **Set up a new phone** (step-up, then C2–C3).
- After a recovery-code sign-in, show the E2 notice on landing: "You signed in with a recovery code. {n} left. Set up your new phone."

### C5. "Turn off account" is one tap, has no confirmation, and sits above Roles
**Screen:** G2 person detail (`user-detail-390.png` and `-1280.png`).
**What happens (Nadia):** the first control under the person's name is a full-size **Turn off account** button, and it posts immediately. Turning off ends sessions and blocks sign-in (Q-052). One mis-tap on a phone while scrolling to the roles turns off Kevin's account, with no reason recorded (`reason=""`). The screenshots also show it on an *Invited* account, where the relevant actions are Resend and Cancel invitation.
**Fix:**
- Move account actions to the bottom of the page, or into an overflow menu labeled "More actions", as G2 specifies.
- Put Turn off behind a confirm step: "Turn off Kevin Thompson's account? He'll be signed out everywhere and can't sign in until an Administrator turns it back on. Upcoming commitments are cancelled and leaders are told." Include a required short reason and a Danger button **Turn off account** next to a Ghost **Keep account on**.
- For Invited accounts, show **Resend invitation** and **Cancel invitation** instead.

---

## Major

### M1. Messages on signed-out screens never show, then pop up later out of context
**Screens:** A1, A2, C4, C1–C3 (`base_public.html` doesn't render `messages`).
**What happens:**
- **Kevin taps Resend:** nothing visible happens. Within the 30-second cooldown nothing is sent either, because `request_sign_in` returns `"cooldown"` and the view ignores it. Later, "Sent again. Use the newest email." appears on his Home.
- **Ruth after 5 wrong authenticator codes:** she is dropped on a blank sign-in screen with no explanation, and after she signs in, Home shows "For your safety, please start again from your email **(PRD-GAP Q-072)**". That leaks an internal ID into user copy.

**Fix:**
- Render messages in `base_public` as `role="status"`.
- Add an A4-style lockout state: h1 "Let's start again from your email", body "That code didn't match a few times, so for your safety we need a fresh sign-in email." Prefill the email field.
- Remove "(PRD-GAP Q-072)".
- For Resend, show "You can resend in 0:24" and disable the button during the cooldown. After a real send, say "Sent again. Use the newest email."

### M2. The email address is never prefilled, and the return destination can be lost
**Screens:** A1, A2 "Wrong email? Change it", A3 expired link.
**What happens (Kevin, journey 2.1):**
- A1 has no `value`. After a validation error, the typed address disappears.
- The hidden `next` field is only emitted from `request.GET.next`, but the form posts to `/sign-in` without the query string. **A second submit after an error drops the deep link**, so Kevin lands on Home instead of the invitation.
- "Change it" and "Email me a new link" both open a blank field.
- Resend passes `ham_pending_next`, which is never set before MFA, so **a resent email also loses the deep link**.

**Fix:**
- Always re-render `value="{{ email }}"` and `next` from the view context, not from `request.GET`.
- Store `next` in the session at A1 and use it for Resend.
- Prefill A1 from the session email on "Change it" and on A3. On A3, show the address masked from the link's token.

### M3. Samuel is forced into setup with no "not now", and the Sign out button doesn't really sign him out
**Screens:** C1–C3 (`mfa_setup_connect.html`).
**What happens:**
- The spec (Q-045) keeps non-MFA access until enrollment and tells the person so. The build forces setup at sign-in with no way through, so **Samuel loses his volunteer access** at a meeting without his phone.
- **Sign out** posts to a guarded route while he is still unauthenticated. The guard bounces him to `/sign-in?next=/sign-out`, and **the pending-MFA session keys stay in the session** on the shared church-office laptop. That is a hand-off to ham-privacy-security-reviewer.
- The page merges C1 and C2 and doesn't name the role.
- There is no **Open my authenticator app** (`otpauth://`) button or **Copy key**. On a phone, Ruth has to retype a 32-character key.
- After a wrong code, **the QR disappears** because `qr_svg=""`.

**Fix:**
- Add "Can't do this now? **Continue as a volunteer**. Your {role} access starts once you're set up." Show it only if the person holds a non-MFA role.
- Make Sign out a public route that clears the pending state and shows J2.
- Add the step label "Step 1 of 2 · Connect the app" and "Your role as {role} needs…".
- On a phone, make **Open my authenticator app** a Secondary lg button and add **Copy key**. Show the key in 4-character groups.
- Re-render the QR after an error.

### M4. Recovery codes can't be downloaded, printed or copied
**Screen:** C3. Only a list and a checkbox.
**Fix:** add **Download** (a .txt file named "{church.shortName} HAM recovery codes"), **Print** and **Copy all** as Secondary buttons, and keep the checkbox. Copy: "Keep them somewhere safe, like with your important papers."

### M5. Raw exception text and internal codes appear in the UI
**Screens:** invite, role confirm, impersonate, MFA reset (`str(exc)` is rendered), audit list and detail, G2 "Recent access changes".
**What happens (Marcus, Nadia):**
- Error text such as "user.invite: an Assistant Director may only invite as Volunteer (PRD-GAP Q-082)" can reach the screen.
- The audit list and detail show `role.granted`, `user <uuid>` and `auth.sign_out`.
- The audit Action filter asks people to type internal codes ("Action (e.g. role.granted)").

**Fix:**
- Map domain errors to user copy in the view layer, and never render `str(exc)`.
- Add a label map from action code to plain phrase ("Changed roles", "Signed out", "Exported audit log").
- Show subjects ID-first ("Ruth Alvarez (user)", "HAM #037").
- Make Action a grouped select using the H1 groups.

### M6. Times are UTC with no label, so leaders read them 4 hours off
**Screens:** G2 "Last signed in", audit list "When", trusted devices "Trusted until".
**What happens:** `TIME_ZONE="UTC"` and nothing activates the church time zone (`ChurchProfile.time_zone`). The audit list shows UTC with no label, so a 7:48 PM event reads as 11:48 PM. Audit date filters parse as UTC midnight. The detail page appends "UTC" correctly, but it doesn't show local time.
**Fix:** add middleware that activates `church.time_zone`, then format times as "Oct 6, 7:48 PM". Audit detail shows local time with the zone plus UTC. Date filters are interpreted in local time (PRD §70.5).

### M7. The audit log isn't usable for journey 2.7, especially on a phone
**Screen:** H1 (`audit-log-390.png`).
**What happens (Marcus):**
- There are no presets and no User or Project filter controls. `?user=` only works from the G2 link.
- The date inputs have no visible labels (the "mm/dd/yyyy" pair is unlabeled).
- The filter inputs are about 20px tall at 390, which fails 2.5.8 in spirit and makes them hard to tap.
- Export is CSV only, has no summary of what will be exported and no PII note, and shows even with 0 events.

**Fix:**
- Add visible labels "From" and "To", a date preset select (Today, Last 7 days as default, Last 30 days, Custom), a User search, a Project ID field and the grouped Action select.
- Give all filter controls the `control-md` height (48px) and let them stack full-width on mobile.
- Before step-up, show a short Export step: "Uses your current filters: Last 30 days · Budget · 3 events. The file includes event IDs and staff names, not requester names or addresses." Hide or disable Export when there are 0 events, with the reason stated.

### M8. There's no sign-out in the app shell, and "Sign out everywhere" signs out only this device
**Screens:** base shell and F.
**What happens:**
- The only sign-out is inside Me → Sign-in & security, under a heading "Sign out everywhere", but the button posts to the ordinary `sign_out`, so other devices stay signed in. For Ruth, who thinks she has cut off a lost phone, that is a false sense of safety.
- There are no trusted-device names, no "this device" marker and no per-row **Stop trusting**.

**Fix:**
- Add **Sign out** to the desktop app bar account menu and to Me or More on mobile.
- Either build a real "sign out everywhere" (invalidate all sessions and trusted devices, confirm sheet: "Signs you out on every phone and computer, including this one.") or rename the section to "Sign out of this device" until it exists.
- Show "Chrome on iPhone · trusted until Nov 5 · this device" with **Stop trusting** on each row.

### M9. Role-change confirmation doesn't name the consequences
**Screen:** G3 (page section).
**What happens (Nadia adds Pastor for Ruth):**
- Each change line is just the role description.
- Nothing says Ruth must set up two-step sign-in before her Pastor access starts (Q-045).
- Nothing says what Ruth keeps. The "What can do" list only updates after saving.
- "gets an email about their new role" is printed for removals too, and the email is never sent (C3).
- The success toast is "Roles updated." with no name or time.

**Fix:**
- For an MFA role, add: "Ruth will need to set up two-step sign-in the next time she signs in. Her Pastor access starts then."
- Add a line "After this change, Ruth can:" followed by the union summary.
- Word the email line as "Ruth gets an email about this change." and only show it once the email exists.
- Toast: "Roles updated for Ruth Alvarez · 7:48 PM".

### M10. Impersonation start makes Nadia type more than needed, and the copy is vague
**Screen:** I1.
**What happens:**
- The reason field is free text with no chips.
- The copy says "recorded as you acting as them" instead of the actual names.
- Nothing says Kevin will be told (Q-049).
- After step-up the form is empty again (C1).
- Ending the session returns her to Home instead of Kevin's page, with the toast "lasted 0 min."

**Fix:**
- Add reason chips that prefill an editable field: Can't see an invitation · Notification problem · Check-in problem · Profile or credential problem · Something else.
- Copy: "Everything you do is recorded as Nadia Pierre acting as Kevin Thompson."
- On return, land on Kevin's G2 with "You're back as Nadia. Troubleshooting as Kevin lasted under a minute."

### M11. Invite: a duplicate email probably crashes, and field errors aren't tied to their fields
**Screen:** B7 invite page. `User.email` is unique, and `invite_user` calls `User.objects.create` without catching `IntegrityError` **(verify)**.
**Fix:** check for the address first and show the B7 inline message: "Dwayne Carter already has a HAM account. [Open profile]". Add `aria-invalid` and `aria-describedby` to each field error, as `me.html` already does.

---

## Minor

1. **A2** is missing the "Didn't get it?" help: "Check your spam or promotions folder. The email comes from {sender}. It can take a minute. Still nothing? Contact {church.hamEmail}."
2. **A5 rate limited:** `retry_at` is passed but not shown. Add "You can ask for another at 3:42 PM."
3. **Link interstitial** ("Continue signing in"): keeping it to guard against mail-scanner prefetch is reasonable, but it costs 1 extra tap. Tell the person where they're going: "Continue to HAM". If the device is already signed in, skip the interstitial and go straight to the destination (A3 rule). The expired copy should say "for {n} minutes", not "for a limited time".
4. **C4 wrong code:** say "That code didn't match. Codes change every 30 seconds, so try the current one." After 3 tries, add the phone-clock hint.
5. **Step-up** uses an h2 with no h1. The label "Authenticator code" should be "Code from your authenticator app". "Use a recovery code above instead" points the wrong way; say "Lost your phone? You can type a recovery code in the same box." Render step-up inside the signed-in shell (or as the Q-092-style section) so the person keeps their context.
6. **Two h1s per page:** the app bar title is an h1 and so is the content heading. Make the app bar title a `<p>` or `<span>`. Home's empty state uses an h3 with no h2.
7. **Inline errors** on sign-in, code, MFA, step-up and invite use `role="alert"` and aren't tied to their fields. Add `aria-invalid` and `aria-describedby`. Spec §6 says code errors should be polite (`role="status"`), and lockouts should be the h1.
8. **Impersonation banner** uses `role="alert"`, so screen readers re-announce it on every page. Use a `region` landmark named "Impersonation" and prefix `<title>` with "Acting as Kevin Thompson · " (spec §6).
9. **Users list on mobile:** the Two-step value "Not needed" loses its column header. Render it as "Two-step: Not needed". Add the "Two-step: Not set up" filter chip, which is the list Nadia actually needs.
10. **G2** puts "Review changes" below Leads projects and What can do. On mobile, put a sticky "1 change · Add Pastor [Review]" bar at the bottom, or move the button directly under the roles.
11. **Signed out (J2):** add **Forget my email on this device** once A1 remembers an email.
12. **"Troubleshooting ended · lasted 0 min."** Use "under a minute" for durations under 60 seconds.

---

## Assessment of the logged gaps

| Gap | Verdict | Condition to accept |
|---|---|---|
| **Q-084** invitation merged into sign-in, no Welcome screen | **Accept the simplification for V1, but not as built.** One path in is simpler for unpaid volunteers, and it's fine to drop B1. It can't ship while no invitation email exists (C3). | (1) Send an invitation email that names the inviter and the church (the "is this legit?" hesitation). (2) On first sign-in (Invited → Active), show a one-time Home notice: "Welcome to HAM, Dwayne. Luis Romero invited you. A few quick steps and you're ready to serve." with a link to confirm the name in Me. (3) A3 with the email prefilled (M2) stands in for B3 "expired, send a new one". B6 (wrong person signed in) is handled by the existing `sign_in` redirect only if the link flow signs out first; add a line on the interstitial: "You're signed in as Kevin. Continue as d•••@example.com?" |
| **Q-091** Admin bottom nav shows 7 flat items | **Reject.** It hides Me and Audit log on phones and makes sign-out unreachable (C2). | Build Home · Admin · Inbox · More now, with the Admin index as a plain list page, plus a nav cap of 5 in `nav_for`. |
| **Q-092** role confirm is a page section, not a sheet | **Accept for V1.** A server-rendered confirm step works without JS, is keyboard-operable, and costs the same number of clicks. | Move focus to the confirm heading on load (`id` + `tabindex="-1"`, plus `#confirm-title` in the URL). Keep the roles visible as a read-only summary above it. Move the Account and Turn off controls out of the way (C5). Fix Cancel (C1). |

---

## Journey scorecard (spec target → as built)

| Journey | Target | As built |
|---|---|---|
| 2.1 Kevin, sign in from email | 1 tap send + 1 tap link, 0 typed | 1 tap send + link + **Continue** tap (3). The email isn't prefilled, and the deep link is lost after an error or a resend (M2). |
| 2.3 Ruth, two-step on phone | + 6 digits | Works: link → Continue → code → Verify, with the trust checkbox. The lockout message is invisible (M1). |
| 2.4 Samuel, first sign-in with role | Email tells him; 3-step setup; "later" keeps volunteer access | **No email (C3).** Setup is forced with no "later", the key has to be typed on a phone, and codes can't be saved easily (M3, M4). |
| 2.5 Marcus, lost phone | Recovery code or ask an Administrator; re-enroll | **Dead end without codes; no re-enroll with codes (C4).** |
| 2.6 Nadia, change roles | 4 clicks + 6 digits, consequences named | The click count matches. Consequences are thin (M9), and Cancel loops (C1). |
| 2.7 Marcus, export audit log | 3 clicks after filters | **Export ends in 405 (C1).** Filters need internal codes and times are UTC (M5–M7). |
| 2.8 Nadia, troubleshoot as Kevin | overflow → chip → Start → 6 digits | The reason has to be typed twice (C1, M10). The banner and blocked actions are present. |

## Hand-offs
- **ham-privacy-security-reviewer:** pending-MFA session keys persist after "Sign out" on the setup screen (M3); "Sign out everywhere" doesn't end other sessions (M8); raw exception strings in the UI (M5).
- **ham-frontend-engineer:** C1, C2, C5, M1–M11.
- **ham-backend-engineer / ham-integrations-engineer:** the invitation and role-change emails (C3); church time zone activation (M6); duplicate-email handling (M11).
- **ham-ui-designer:** re-capture `step1-screens` after the fixes. The current PNGs predate S3b.
