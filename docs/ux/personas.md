# HAM personas

Build-order step 0. Owner: ham-ux-designer. Implements the role definitions in PRD §4, the auth rules in §60, the permission principles in §67 and the privacy rules in §68.
All names are fictional. Local time is America/New_York, stored in UTC (§70.5).
Open-question status follows `docs/prd-open-questions.md` (owner decisions of 2026-09-27). Still open: Q-001, Q-003, Q-025.
HAM is single-church in V1. Church naming and branding come from the church profile (Q-026), so generic copy uses `{church.name}` / `{church.shortName}`. Miami Temple appears only as sample data.

## How to use this file
- Design every screen for one **primary persona**, then check it against the others who can reach it.
- The **Must never see** line for each persona is a design constraint. Enforcement happens server-side (§67, §68). Hiding something in the UI is not a control.
- "Role" means a permission set. "Persona" means a typical person holding that role. One person can hold several roles (§4.11). See [Combined roles](#combined-roles) at the end.

## Quick reference

| Persona | Role (§4) | Auth (§60) | Main device | Frequency | Opens on |
|---|---|---|---|---|---|
| Doris, requester | 4.1 Requester | Secure link + email code (email only in V1, Q-019; no-email case open, Q-025) | Phone, sometimes a relative's | A few times per request | Her request page |
| Elder Samuel, Board rep | 4.2 | MFA | Laptop at meetings, phone | Around Board meetings, monthly | Decisions to record |
| Pastor Ruth | 4.3 | MFA | Phone | Weekly, plus urgent pings | Approvals & urgent |
| Marcus, HAM Director | 4.4 | MFA | Desktop, phone on site | Daily | What needs attention |
| Andre, Assistant Director | 4.5 | MFA | Desktop + phone | Several times a week | What needs attention |
| Luis, Project Leader | 4.6 | Passwordless | Phone | Daily near a project | Today / my projects |
| Tom, Task Leader | 4.7 | Passwordless | Phone | Project days | My task on today's project |
| Kevin, volunteer | 4.8 | Passwordless | Phone | Weekly or less | Next action |
| Bayside Plumbing, contractor | 4.9 | Passwordless, project-limited | Phone | Per assignment | Assigned task |
| Grace, Social Media Specialist | 4.10 | Passwordless (not in §60.1 MFA list) | Phone | After projects | Media to review |
| Nadia, Administrator | 4.11 | MFA | Desktop | Occasional | Users & system health |

---

## Requester / homeowner: Doris Pennington (§4.1, §6, §7, §41, §45, §48, §54)
- **Who:** 74, widowed, on a fixed income. Not a church member. Her roof leak is soaking the bedroom ceiling. She may be stressed or embarrassed to ask for help. Sometimes her daughter helps as an *authorized family member* (§6.2).
- **Device/context:** Older Android phone, large font setting, spotty home Wi-Fi. Opens emails and texts. Does not install apps.
- **Frequency:** Submits once, then returns 3–8 times through the secure link (status, uploads, agreement, schedule, survey).
- **Top jobs:** Ask for help without feeling judged. Know what happens next and when. Upload photos when asked. Sign the service agreement. Know who is coming and when. Say whether the problem was fixed.
- **Must never see:** Internal comments, approver deliberation, the duplicate/history alert (§9), volunteer names beyond what scheduling requires (proposal: Project Leader first name + arrival window only; no official Q yet), reliability scores, budget internals beyond her own payor share (§13).
- **Auth:** No account (§7, §60.3). A request-specific secure link is valid until 7 days after completion. After that she re-verifies by **email code** and gets a new 14-day link, which kills the old one (§7.3). She must verify before uploading media (§7.1, §45). V1 uses email codes only; there are no SMS codes (Q-019, decided).
- **Open (Q-025): no email address.** Doris may not have email of her own. How a requester without email verifies for media upload or gets a new link is **not decided** (options: leadership verifies by phone and records it / a family member's email / an SMS provider for codes only). Until Q-025 is decided, designs must not assume every requester has email, and must not invent a workaround. Step 2 (Intake) will propose one.
- **Reaching HAM:** her page always shows the ministry phone and email, set by an administrator in the church profile (Q-007, decided). No in-app messaging.
- **Cost-share increase:** she can approve on her secure page, or tell the Project Leader, who records her verbal approval. Both are audited (Q-008, decided).
- **Design notes:** One page, no navigation to learn, big touch targets, plain words, compassionate copy (§8.3). Never use a word like "ineligible" without explaining it kindly.

## Board of Elders representative: Elder Samuel Okafor (§4.2, §8.1, §8.4, §14.2)
- **Who:** Retired accountant. He records decisions the Board already made in its meeting. He does not decide in HAM.
- **Device/context:** Laptop during or after the monthly Board meeting. Phone for notifications.
- **Top jobs:** Record Approve/Reject plus a reason for each request the Board reviewed. Record reconsideration outcomes. Record the Board-approved church contribution (amount, date, reference). Occasionally view project oversight information.
- **Must never see:** Deleted-comment content (§57), volunteer feedback (§55), and the audit log beyond his own actions. Serious incidents reach him only if a pastor decides to notify him (§56).
- **Auth:** MFA required (§60.1). On the Google Calendar audience (§51).
- **Design notes:** Batch entry: a list of the "Board review" queue with one decision row per request. Show enough context to confirm he has the right request (ID, category, urgency, a short need summary, prior-assistance note from §9).

## Pastor: Pastor Ruth Alvarez (§4.3, §8.2, §10, §47.4, §56)
- **Who:** Associate pastor who knows many families personally. Busy. Often gets an urgent request call in the evening.
- **Device/context:** Phone, between visits.
- **Top jobs:** Approve or reject requests on the pastoral route. **Certify urgency** fast. Handle reconsiderations of her own rejections (§8.4). Decide whether serious incidents go to the Board rep. Approve media publication (§47.4).
- **Must never see:** Deleted comments (§57), volunteer feedback (§55), admin settings.
- **Auth:** MFA (§60.1). A trusted phone is remembered for 30 days, so she isn't re-challenged every time (Q-010, decided).
- **Design notes:** Approving urgent requests must take 3 taps or fewer from the notification. Show why the requester says it's urgent. Show history context (§9) as information, never as an automatic "no".

## HAM Director: Marcus Bell (§4.4, §12, §13, §57, §58, §64)
- **Who:** Volunteer director who runs HAM in the evenings after his day job. He is the only person who can redefine scope or decline execution.
- **Device/context:** Desktop at home, 1440px. Phone on site for assessments (§11) and on project days.
- **Frequency:** Daily, 10–20 minutes.
- **Top jobs:** Triage what needs him. Make feasibility decisions and scope changes. Clear safety holds. Watch staffing around the 48-hour line. Respond to incidents. Oversee budgets. Export the audit log.
- **Can see:** Requester identity and address. Deleted comments. Volunteer feedback. Everything operational (§67). He is the one role whose reveals of requester PII on leadership screens are **not** audit-logged (Q-024, decided).
- **Must never see / must never cause:** Requester PII on shared surfaces such as the calendar, the member scoreboard, the public scoreboard embed or aggregate reports (§51.1, §63, §68). When he projects his screen in a leadership meeting, PII could be visible. Attention rows are ID-first by design; a "hide names" presentation mode is deferred.
- **Auth:** MFA (§60.1). Trusted device remembered 30 days; always re-checked for audit export and role changes (Q-010).

## HAM Assistant Director: Andre Whitfield (§4.5, §12, §24, §39)
- Like Marcus, with broad operational rights (he can review and upload media but **cannot approve publication**; §47.4 approvers are the Social Media Specialist, HAM Director and pastors), but he **cannot** redefine scope or finally decline execution. He *recommends* instead (§12). He can place projects On Hold and clear safety holds (§39). He verifies credentials manually when auto-verification isn't available (§24). He edits budgets (§14.3).
- He cannot see deleted comment content (§57). He can see volunteer feedback (§55).
- He can see requester PII on leadership screens, and each reveal (hover card or side panel) is audit-logged (Q-024).
- **Design notes:** Same dashboard as the Director. Director-only actions appear as "Recommend …", never as a disabled button with no explanation.
- **Auth:** MFA.

## Project Leader: Luis Romero (§4.6, §16, §18, §29–§31, §37, §38, §53)
- **Who:** Contractor by trade. He leads 1–2 projects a month and often also leads a task (§4.6).
- **Device/context:** Phone on site: sunlight, dusty hands or gloves, one hand holding a ladder. Weak signal inside some homes.
- **Top jobs:** See today at a glance. Run the safety checklist (§38). Show the check-in QR and correct attendance (§37). Move tasks. Handle last-48h staffing (§30). Reassign or replace volunteers (§31). Create justified unplanned tasks (§18). Complete the project (§53).
- **Can see (assigned projects only):** requester name, address, phone and hazards (Q-009, decided). Each reveal is audit-logged (Q-024). Not the requester's circumstances beyond that (for example financial situation or approval deliberation).
- **Must never see:** Volunteer post-project feedback (§55), deleted comments, the audit log or a per-project activity history (§58, §67; Q-021 decided: No), projects he is not assigned to (§67 "project-specific").
- **Auth:** Passwordless (§60.2). No MFA solely for being a Project Leader (§60.1). Because he sees requester contact details without MFA, requester fields stay scoped to his assigned projects and reveals are logged.
- **Reachable by his crew:** assigned volunteers see a Call button for him the day before and the day of the project only (Q-023).

## Task Leader: Tom Nguyen (§4.7, §15.5, §17, §53)
- **Who:** Skilled drywaller. Task Leader is **assigned per task, not a standing role**. On one project Tom is a Task Leader; on the next he is a plain volunteer.
- **Top jobs:** See his task's requirements, tools, materials and crew. Move the task to In Progress, Blocked (with a reason) or Completed. Complete or cancel his follow-up tasks (§53).
- **Can see (projects/tasks he is assigned to only):** the same requester details as the Project Leader: name, address, phone and hazards (Q-009, decided). Each reveal is audit-logged (Q-024). Access ends when he is no longer assigned.
- **Must never see:** Budget, other projects, volunteer feedback, requester circumstances beyond name, address, phone and hazards.
- **Auth:** Passwordless.

## Volunteer: Kevin Thompson (§4.8, §20–§35, §37, §42, §43)
- **Who:** 38, electrician's helper, member of the Men's Ministry. Volunteers about once a month. Wants to help without paperwork.
- **Device/context:** Phone, often at lunch break or in a truck. Opens HAM from an email notification about 70% of the time.
- **Top jobs:** Accept or decline invitations before the deadline (§28). Reconfirm 7 days out (§32). Know where and when to show up. Check in and out on site (§37). Keep his credentials current (§24.1). Finish onboarding (§42). Cancel honestly when he must (§33). Give feedback (§55). Understand his reliability score (§34).
- **Must never see:** Other volunteers' reliability scores. Requester circumstances and contact details. Budgets. Requests not yet approved. Projects he isn't invited to or assigned to (§67). The full address before assignment: invitations show area + distance, and the full address appears once he is assigned (Q-004, decided).
- **Can see when assigned:** the Project Leader's Call button, the day before and the day of the project only (Q-023).
- **Auth:** Email magic link. Email only in V1; no SMS (§60.2, §75, Q-019).
- **Weak signal:** he can check in offline. The check-in is queued as "waiting to sync" and sent when he reconnects; the Project Leader can correct it (Q-006, §37.2).
- **Media release:** mandatory. If he withdraws it, his profile becomes **inactive** until he restores consent (§43).
- **Design notes:** Home opens on his next action (see [navigation.md](navigation.md#4a-volunteer-home--phone-390px)). Onboarding gaps block participation, so they sit at the top, framed as "almost ready", not as errors.

## Contractor / professional: Bayside Plumbing (contact: Ray Delgado) (§4.9, §40)
- **Who:** Licensed plumber who donates a discounted repair. Uses a limited project-specific account. Some contractors are vendor/expense records only and never log in.
- **Top jobs:** Accept the contractor terms (§40.1). See the address, requester contact and task details for **assigned** work only. Know the date and time.
- **Must never see:** Any other project, volunteer data, budget beyond his own line (if any), incidents.
- **Blocking rule shown in the UI:** He cannot start work until the Project Leader records "Liability insurance verified: Yes".
- **Auth:** Passwordless. The account is scoped to assignments (§4.9).

## Social Media Specialist: Grace Mensah (§4.10, §47.4, §48, §49)
- **Top jobs:** Upload project photos from her phone. Review media. See each item's consent status (internal/public, per item, guardian consent for minors). Approve publication. Categorize media.
- **Must never see:** Requester name, address or circumstances "unless operationally required" (§49). She sees project ID, category and media only. Also no budgets, incidents or volunteer data.
- **Blocking rule:** Publication is impossible without the requester's per-item public consent (§48), plus guardian consent if minors appear. Leadership cannot override this.
- **Auth:** Passwordless (§60.2). She is not in the §60.1 MFA list, so no MFA.

## Administrator: Nadia Pierre (§4.11, §58, §59)
- **Who:** Church IT volunteer.
- **Top jobs:** Maintain the church profile (name, logos, contact info including the ministry phone and email shown to requesters; Q-007, Q-026). Manage users, roles and permissions. Handle integrations (Calendar status, credential verification provider). Change system settings. Troubleshoot through impersonation (reason required, 15-minute idle timeout, dual identity in the audit trail) (§59). Export the audit log. See deleted comments.
- **Must never do while impersonating:** Role or permission changes, privileged budget approvals, protected admin actions (§59).
- **Auth:** MFA.

---

## Combined roles
PRD §4.11: a person may hold several roles, and the **higher-privilege permission applies** when roles conflict.

Common combinations:

| Person | Roles | Consequence for navigation |
|---|---|---|
| Kevin | Volunteer + Task Leader on project #031 | Volunteer nav. The task appears inside the project with a "You lead: Drywall patch" chip. No extra tab. |
| Luis | Volunteer + Project Leader (+ Task Leader) | Leader nav. His own volunteer commitments appear on Home under "Your service". |
| Marcus | Director + Volunteer | Leadership nav. "Your service" strip on Home, below the attention items. |
| Pastor Ruth | Pastor + Volunteer | Approver nav plus "Your service". |
| Nadia | Administrator + Volunteer | Admin area in the sidebar or More menu. Impersonation is never the way she does her own volunteering. |

Rules (detailed in navigation.md §3):
1. **No role switcher.** The app shows the union of what the person can do. People think "what do I need to do?", not "which hat am I wearing?", and a switcher adds a tap and a way to miss things.
2. **Authority is shown per project.** Each project header carries a chip saying the person's relationship to it: *You're leading*, *You lead a task*, *You're volunteering*, *Oversight*.
3. **Personal commitments never disappear under leadership work.** Anyone who is also a volunteer sees "Your service" on Home and has the same "Me" profile.
