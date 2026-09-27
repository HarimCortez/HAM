# Home Assistance Ministry (HAM)
## Product Requirements Document — Version 1

**Document status:** Implementation baseline  
**Product:** Home Assistance Ministry (HAM)  
**Deployment scope:** Single church  
**Primary users:** Church leadership, HAM leadership, volunteers, project leaders, requesters, contractors/professionals, administrator  
**Language for V1:** English  
**Product principle:** Keep project intake, planning, staffing, execution, and accountability as simple and fast as possible for a volunteer-run ministry.

---

# 1. Executive Summary

Home Assistance Ministry (HAM) is a web application for managing small home-assistance projects performed through the church’s Men’s Ministry.

HAM allows church members and non-members to request assistance when a genuine need exists that cannot reasonably be met by the requester or their family.

The application manages the complete project lifecycle:

Request → Approval → Site Assessment → Planning → Budgeting → Task Creation → Volunteer Matching → Scheduling → Execution → Attendance → Follow-Up → Completion → Reporting.

HAM must balance four priorities:

1. Serve people compassionately and efficiently.
2. Maintain accountability for volunteers, leaders, approvals, decisions, money, and actions.
3. Keep administrative effort low enough for a volunteer-operated ministry.
4. Protect requester privacy and enforce safety, licensing, and authorization requirements.

HAM will operate independently in V1 but will be architected for future integration with the separate Fitness & Accountability application.

---

# 2. Product Vision

HAM should make it possible for ministry leadership to take a legitimate home-assistance request from submission to completed service with minimal administrative friction.

The system should answer, at any point:

- Who needs help?
- Has the need been approved?
- What work is actually required?
- Is it safe and permissible?
- What will it cost?
- Who is paying?
- What tasks must be completed?
- What skills are required?
- Which volunteers are qualified and available?
- Who is committed?
- What tools and materials are needed?
- When will the project occur?
- Who showed up?
- What was completed?
- What remains?
- What did the project cost?
- Was the requester satisfied?
- What ministry impact resulted?

---

# 3. Core Design Principles

## 3.1 Simplicity

The HAM Director, Assistant Directors, Project Leaders, and volunteers are volunteers themselves.

Planning interfaces must therefore avoid unnecessary classification, documentation, and administrative complexity.

Where possible:

- reuse prior projects;
- use templates;
- prefill information;
- use AI suggestions;
- automate matching and notifications;
- automate state transitions;
- require explanations only for meaningful exceptions.

## 3.2 Human authority

AI and automation support ministry leaders but do not replace their judgment.

AI may recommend or draft.

Humans approve decisions concerning:

- project scope;
- budgets;
- staffing overrides;
- safety;
- scheduling;
- publication;
- approvals;
- financial commitments.

## 3.3 Accountability

Meaningful actions must be attributable to the individual who performed them.

The system must retain auditability for approvals, decisions, overrides, deletions, administrative actions, impersonation, financial changes, and incidents.

## 3.4 Privacy

Requester names, addresses, personal circumstances, and other sensitive project information should remain inside HAM unless explicitly required elsewhere.

External systems such as Google Calendar should receive only the minimum information necessary.

## 3.5 Safety and compliance

Legal, licensing, credential, and safety restrictions must take priority over convenience.

They cannot be overridden merely to fill a volunteer position.

---

# 4. Stakeholders and Roles

## 4.1 Requester / Homeowner

May be:

- a church member;
- a non-member;
- an authorized family member;
- a tenant with property-owner authorization.

The person requesting assistance does not need a persistent HAM account.

## 4.2 Board of Elders Representative

Represents the Board of Elders in HAM.

The representative records Board decisions in the system after Board review.

## 4.3 Pastor

Any authorized pastor may directly approve a request.

A pastor may approve and certify urgent requests without waiting for Board approval.

## 4.4 HAM Director

Primary operational authority for HAM.

Responsible for:

- project feasibility;
- project scope;
- assessment oversight;
- planning;
- budget oversight;
- volunteer operations;
- project execution;
- audit visibility;
- ministry management.

Only the HAM Director has final authority to redefine project scope.

## 4.5 HAM Assistant Director

Supports project assessment, budgeting, planning, staffing, holds, credential verification, and execution.

May recommend against a project or place it on hold, but the HAM Director makes the final decision to decline execution or redefine scope.

## 4.6 Project Leader

Responsible for execution of an assigned project.

May also act as a Task Leader.

## 4.7 Task Leader

Every task must have a Task Leader.

The Task Leader must possess the primary skill required for that task.

## 4.8 Volunteer

Maintains a persistent HAM profile containing:

- skills;
- skill proficiency;
- tools/equipment;
- availability;
- travel preferences;
- mentor status when applicable;
- licenses/certifications;
- reliability score;
- agreements;
- participation history.

## 4.9 Contractor / Professional

May participate either:

- as an external vendor only; or
- through a limited project-specific HAM account.

Contractor accounts have access only to assigned projects/tasks.

## 4.10 Social Media Specialist

Responsible for collecting and managing approved project media for church communications.

## 4.11 Administrator

Highest-privilege system role.

Responsible for:

- users;
- roles;
- permissions;
- configuration;
- integrations;
- system settings;
- troubleshooting;
- impersonation;
- audit access.

A person may hold multiple roles.

When role permissions conflict, the higher-privilege permission applies.

---

# 5. Eligibility for Assistance

Requests may be made for church members or non-members.

The fundamental eligibility requirement is:

> A genuine need exists that the requester and their family cannot reasonably meet themselves.

Eligibility may be determined by:

- the Board of Elders; or
- pastoral staff.

There is no fixed limit on how many times a household may receive assistance.

Each request is evaluated independently according to need.

Previous HAM assistance history is visible to authorized approvers for context but is not an automatic disqualifier.

---

# 6. Request Intake

HAM V1 shall support:

- a public request form accessible from the church website;
- direct church-issued links/codes to the same request form.

Both paths use the same approval workflow.

## 6.1 Core requester information

The request shall capture at minimum:

- requester name;
- email;
- mobile phone;
- preferred communication method;
- service address;
- relationship to property;
- description of need;
- urgency request if applicable;
- urgency justification;
- known site hazards;
- property type;
- preferred availability;
- supporting media.

## 6.2 Property authority

The requester must certify that they have authority for HAM to perform work.

### Owner

May authorize directly.

### Authorized family member

Must:

- identify the property owner;
- certify that the owner has authorized the request.

Separate owner confirmation is not required by default.

### Tenant

Must obtain written authorization from the property owner or landlord before work begins.

### HOA / condominium / management restrictions

The requester is responsible for obtaining any applicable:

- HOA;
- condominium association;
- landlord;
- property-management approval.

HAM does not require uploaded evidence; requester certification is sufficient.

---

# 7. Requester Identity and Access

Requesters do not need persistent accounts.

Each request is managed through a secure request page.

## 7.1 Verification

Media upload requires ownership verification of at least one:

- email address; or
- mobile phone number.

Verification may use:

- email verification link/code;
- SMS one-time code.

## 7.2 Secure request page

The page supports:

- request status;
- requested media uploads;
- responses to HAM questions;
- agreement signing;
- schedule information;
- completion survey.

## 7.3 Link expiration

Normal request access remains available until seven days after project completion.

After that, the requester may self-generate a new secure link after verifying email or mobile ownership.

A regenerated link:

- remains valid for 14 days;
- invalidates the previous request-access link;
- is logged with timestamp and verification method.

---

# 8. Approval Workflow

Normal requests may receive final approval through either route.

## 8.1 Board route

The Board of Elders reviews the request.

The Men's Ministry Board representative records the Board’s decision in HAM.

## 8.2 Pastoral route

Any pastor may directly give final approval.

Only one authorized final approval is required.

## 8.3 Rejection

Rejected requesters receive:

- notification;
- a polite and compassionate explanation;
- the rejection reason;
- an option for one reconsideration.

## 8.4 Reconsideration

Only one reconsideration is allowed.

If originally rejected through the Board route:

- the Board reconsiders;
- the Men's Ministry Board representative records the revised decision.

If rejected by a pastor:

- reconsideration returns to that pastor;
- another pastor may take over if the original pastor is unavailable.

Every reconsideration decision requires a simple reason.

If reconsideration is rejected, the request closes permanently.

The requester may later submit a new request.

---

# 9. Duplicate and Historical Request Detection

HAM shall automatically detect potentially duplicate or substantially similar requests in the background.

The requester is not required to disclose prior similar requests.

A duplicate/similarity alert is visible only to authorized leadership and approvers.

The alert should show relevant prior:

- request;
- outcome;
- rejection/approval reason;
- assistance history.

Duplicate detection does not automatically reject a request.

---

# 10. Urgent Requests

A requester may flag a request as urgent.

Urgency requires justification.

Examples include:

- safety risk;
- active property damage;
- loss of essential utilities;
- urgent accessibility need;
- comparable immediate hardship.

A pastor must review and certify the urgent designation.

Any pastor may approve an urgent request directly.

Urgent approval allows HAM to proceed without waiting for Board review.

Urgent approval triggers immediate alerts to:

- HAM Director;
- Assistant Directors;
- Project Leader when assigned.

Urgent volunteer notifications may use all available communication channels, regardless of normal notification preference.

---

# 11. Mandatory Site Assessment

Every approved project requires a site assessment before execution.

Approval authorizes assessment; it does not guarantee execution.

Project execution depends on HAM leadership determining feasibility.

The assessment must capture:

- problem description;
- photos;
- relevant measurements;
- safety concerns;
- materials needed;
- tools/equipment needed;
- required skills;
- expected volunteer count;
- estimated cost;
- recommended scope;
- licensing/certification requirements;
- permit/inspection requirements.

HAM leadership should be able to perform the assessment efficiently from a mobile device.

---

# 12. Feasibility Decision

After assessment, the project may be:

- feasible;
- placed on hold;
- determined not executable;
- re-scoped by the HAM Director.

Factors include:

- safety;
- required skills;
- qualified volunteer availability;
- tools/equipment;
- materials;
- cost;
- regulatory requirements;
- licensed-professional requirements.

Assistant Directors may:

- place the project on hold;
- recommend against execution.

Final authority to decline execution or redefine scope rests with the HAM Director.

---

# 13. Scope Changes

Only the HAM Director may formally redefine project scope.

If a scope change increases cost, approval is required from the party whose financial contribution increases.

Possible payors:

- requester;
- church;
- shared requester/church.

If only one party’s contribution changes, only that party must approve the increase.

The other contributing party must be informed.

---

# 14. Project Budget

Each project shall contain a simple formal budget.

The goal is cost accountability without creating an accounting system.

## 14.1 Budget categories

Default categories:

- materials and supplies;
- tool/equipment rental;
- outside professional services;
- delivery/hauling/disposal;
- permits/inspection fees;
- safety/PPE supplies;
- miscellaneous;
- contingency.

Each line item can identify the payor:

- requester;
- church;
- shared.

Estimated and actual values should be supported.

A contingency allowance is permitted.

## 14.2 Church contribution

HAM V1 does not implement a separate Board financial approval engine.

Instead, HAM records:

- Board-approved contribution;
- approved amount;
- date/reference as appropriate.

## 14.3 Editing

HAM Director and Assistant Directors may create/edit the project budget.

---

# 15. Project and Task Planning

Projects are broken into tasks.

Planning must remain lightweight.

## 15.1 Required task fields

Each task should contain:

- task name;
- description;
- required skill(s);
- required tools/equipment;
- required materials;
- required volunteer count;
- Task Leader;
- estimated duration;
- optional safety requirement;
- optional licensing/certification requirement.

## 15.2 Tool classification

Tools may be marked:

- required;
- preferred/helpful.

## 15.3 Volunteer requirements

Tasks may define:

- minimum volunteer count;
- skill-specific staffing requirements.

## 15.4 Dependencies

Tasks may depend on other tasks.

Dependent work normally cannot proceed before the prerequisite is complete.

Dependency override is allowed for:

- Project Leader;
- HAM Director;
- Assistant Director.

Override requires written justification.

## 15.5 Task lifecycle

Primary states:

Planned → Ready → Assigned → In Progress → Blocked → Completed

Alternate state:

Cancelled

Blocked status requires a reason.

Suggested blocker categories:

- materials;
- volunteer availability;
- tools/equipment;
- safety;
- weather;
- dependency;
- other.

---

# 16. Project Leadership

Every project has a Project Leader.

The HAM Director or Assistant Directors may assign the Project Leader.

The Project Leader:

- coordinates Task Leaders;
- coordinates volunteers;
- monitors execution;
- may reassign volunteers among tasks;
- may replace volunteers;
- may create urgent unplanned tasks when necessary;
- may update execution status;
- may close the project.

Reassignments must continue to respect licensing, safety, skill, and mentor requirements.

The Project Leader may also lead one or more tasks.

---

# 17. Task Leadership

Every task has a Task Leader.

HAM Director or Assistant Directors may assign Task Leaders.

A Task Leader must possess the primary skill required for the task.

---

# 18. Unplanned Work

The preferred behavior is not to introduce new work during execution.

However, the Project Leader may create a new task if genuinely necessary and if:

- budget permits;
- urgency supports it;
- tools are available;
- materials are available;
- skills are available;
- safety requirements are satisfied.

Every unplanned task requires a short justification.

Any increased financial contribution follows the normal payor-approval rules.

---

# 19. Templates and Reuse

HAM shall optimize planning through reuse.

## 19.1 Task templates

Common work types may have reusable templates.

Examples:

- drywall repair;
- painting;
- faucet replacement;
- yard cleanup;
- furniture movement;
- minor carpentry.

HAM Director, Assistant Directors, and Project Leaders may create/edit proposed templates.

New or materially changed shared templates require HAM Director approval.

Project Leaders may modify a template for one project without altering the master template.

## 19.2 Copy previous project

Leadership may create a new project from a similar previous project.

Copyable structure includes:

- tasks;
- skill requirements;
- tools;
- materials;
- dependencies;
- estimated durations;
- budget categories.

Reset automatically:

- statuses;
- dates;
- assigned volunteers;
- project-specific costs.

---

# 20. Volunteer Accounts

Volunteers have persistent HAM accounts.

Their profiles survive across projects.

A volunteer may temporarily deactivate their profile.

Inactive volunteers:

- remain in historical records;
- are excluded from matching;
- do not receive new project invitations.

Reactivation is immediate.

If required agreements changed while inactive, the volunteer becomes active but remains unable to participate until the current versions are accepted.

---

# 21. Volunteer Deactivation with Future Commitments

When a volunteer deactivates while assigned to future work, HAM asks whether they remain committed.

If they confirm:

- assignment remains.

If they decline:

- assignment is cancelled.

If they do not respond:

- assignment is automatically cancelled.

Automatic cancellation caused by profile deactivation does not reduce reliability score.

---

# 22. Volunteer Skills

Volunteers maintain their own skill inventory.

For non-licensed skills, volunteers self-identify proficiency.

HAM leadership may add a separate observed/verified skill level without replacing the volunteer’s self-assessment.

Volunteer profiles also include skills the volunteer wants to learn.

---

# 23. Mentor / Apprentice Program

HAM supports explicit mentor/apprentice assignment.

A skilled person is not automatically a mentor.

Mentor status must be explicitly assigned by:

- HAM Director; or
- Assistant Director.

A mentor must meet the qualification threshold for the relevant task.

For licensed work, mentor status does not replace any legal licensing requirement.

---

# 24. Licenses and Certifications

Volunteers may enter their own licenses and certifications.

HAM should automatically verify credentials against authoritative online sources whenever technically available.

Fallback verification may be completed by:

- HAM Director;
- Assistant Director.

Credential records should contain:

- credential type;
- issuing authority;
- credential/license number;
- expiration date;
- verification status;
- verification source;
- verification date.

Expired credentials block only tasks requiring that credential.

They do not block unrelated HAM participation.

## 24.1 Expiration alerts

Volunteer alerts:

- 60 days;
- 30 days;
- 7 days before expiration.

HAM Director and Assistant Directors also receive relevant alerts.

Project Leaders receive alerts when an assigned volunteer’s required credential may expire before the project.

The system warns but does not automatically remove the volunteer.

The Project Leader can replace them.

Legal credential requirements cannot be overridden.

---

# 25. Volunteer Tools and Equipment

Volunteers may record tools/equipment they personally own and are willing to bring.

HAM V1 will not maintain a centralized church-owned tool inventory.

Task planning identifies required and preferred tools.

Volunteer matching considers the volunteer’s available tools/equipment.

---

# 26. Volunteer Availability and Travel

Volunteer profiles support:

- general availability;
- preferred days/times;
- unavailable dates;
- maximum travel distance;
- maximum travel time.

Volunteer matching considers both project distance and travel preference.

---

# 27. Volunteer Matching

Matching considers:

- required skills;
- preferred skills;
- tools/equipment;
- licenses/certifications;
- mentor status;
- availability;
- travel preference;
- distance;
- reliability score.

The interface shall explain why a volunteer matched.

It shall not display a single artificial “match percentage.”

The user should see underlying factors instead.

## 27.1 Required vs preferred criteria

Required criteria determine automatic invitation eligibility.

Preferred criteria improve suitability.

A volunteer who fails a normal required criterion is excluded from automated invitations but may be reviewed manually by the Project Leader.

Manual override requires a short reason.

Never-overridable requirements include:

- legally required credentials;
- safety-critical requirements;
- required mentor conditions where mandated for safety.

---

# 28. Automated Volunteer Invitations

HAM automatically invites qualified matched volunteers.

Project Leader may override the selection.

Invitations support:

- Accept;
- Decline.

Assignments are filled first-come, first-served among qualified invitees.

Each invitation has a response deadline.

If the volunteer declines or fails to respond, HAM may automatically invite the next qualified volunteer.

---

# 29. Volunteer Capacity and Waitlist

When required staffing is filled, later qualified volunteers move to an automatic waitlist.

When an assigned volunteer cancels:

- first qualified waitlisted volunteer is promoted;
- promoted volunteer receives Pending Confirmation status;
- Project Leader is notified;
- volunteer is notified.

Promoted volunteer has 24 hours to confirm.

If no confirmation occurs, the next qualified person is offered the slot.

Automated cycling continues until the project is within 48 hours of execution.

Inside the last 48 hours, staffing becomes Project Leader controlled.

---

# 30. Final 48-Hour Staffing

Within 48 hours of the project:

- Project Leader may directly invite or assign any qualified volunteer;
- volunteer must be notified;
- explicit pre-acceptance is not required;
- volunteer may decline;
- declining such an unsolicited last-minute assignment does not affect reliability.

---

# 31. Project Leader Staffing Overrides

Project Leader may:

- remove an accepted volunteer;
- replace an accepted volunteer;
- select another qualified volunteer;
- use normal matching;
- manually select a qualified volunteer.

All legal and safety requirements remain enforced.

---

# 32. Volunteer Commitment Reconfirmation

Accepted volunteers must reconfirm participation seven days before the project.

If no response:

- HAM retains the slot;
- follow-up reminders are sent.

If still unconfirmed five days before the project:

- the slot is released;
- the first qualified waitlisted volunteer is promoted;
- that volunteer receives Pending Confirmation.

The promoted volunteer receives 24 hours to confirm.

---

# 33. Volunteer Cancellation

Volunteers may cancel in the app.

Cancellation at least seven days before the project produces no reliability penalty.

Inside seven days, penalty increases as the project approaches.

Same-day cancellation has a substantial penalty but remains slightly less severe than a no-show.

No-show carries the highest reliability penalty.

HAM Director, Assistant Directors, and Project Leader may mark a cancellation/no-show as excused.

Excused events do not reduce reliability.

Excusing an event requires a reason/comment.

---

# 34. Volunteer Reliability Score

HAM displays a single volunteer reliability score from 0–100.

Visible to:

- volunteer;
- HAM leadership.

The system also explains how the score is calculated and what participation events affected it.

The scoring weights are fixed system rules, not administrator-configurable.

## 34.1 Recommended V1 scoring model

Initial score: 100.

Suggested fixed event impacts:

- completion / attendance as committed: maintain score;
- cancellation ≥7 days: 0 penalty;
- cancellation 4–6 days: small penalty;
- cancellation 2–3 days: moderate penalty;
- cancellation 1 day before: larger penalty;
- same-day cancellation: major penalty;
- no-show: largest penalty;
- excused event: 0 penalty.

The exact numeric weights should be centralized in application configuration/code and versioned so the behavior is deterministic and testable.

The score should recover gradually through future fulfilled commitments rather than remaining permanently reduced.

---

# 35. Notifications

Users may select one or multiple preferred channels:

- email;
- SMS;
- in-app.

In V1:

- HAM supports email and in-app;
- SMS will later be delivered through Fitness & Accountability integration.

Urgent notifications may use every available supported channel regardless of normal preference.

Requester notifications include:

- request received;
- approval;
- rejection;
- request for additional information;
- scheduling;
- rescheduling;
- project hold;
- project completion.

Volunteer notifications include:

- invitations;
- assignment;
- waitlist promotion;
- reconfirmation;
- reminders;
- schedule change;
- credential expiration;
- cancellation/replacement;
- relevant urgent alerts.

---

# 36. Fitness & Accountability Application Architecture

Fitness & Accountability is a separate application with a distinct purpose.

A person may belong to:

- HAM only;
- Fitness & Accountability only;
- both.

## 36.1 Shared identity

Both applications should share a common identity/authentication layer.

Shared basic profile:

- name;
- email;
- mobile;
- notification preferences.

Each application maintains its own ministry/domain profile.

## 36.2 Ownership

HAM is authoritative for:

- HAM requests;
- HAM projects;
- HAM assignments;
- HAM commitments;
- HAM attendance;
- HAM reliability;
- HAM service history.

Fitness & Accountability is authoritative for its own fitness/accountability domain.

## 36.3 Future role

Fitness & Accountability will assist HAM with:

- reminders;
- commitment reinforcement;
- follow-up;
- accountability;
- SMS.

It does not become HAM’s source of truth.

## 36.4 Versioning

Direct Fitness & Accountability integration is deferred beyond HAM V1.

V1 must nevertheless be integration-ready through clean APIs/events.

Candidate HAM events include:

- VolunteerInvited;
- VolunteerAccepted;
- VolunteerDeclined;
- ReconfirmationRequired;
- VolunteerCancelled;
- VolunteerReplaced;
- ProjectStartingSoon;
- VolunteerCheckedIn;
- VolunteerCheckedOut;
- VolunteerNoShow;
- ProjectCompleted.

HAM must remain fully functional if the Fitness application is unavailable.

---

# 37. Volunteer Attendance

HAM supports both self-check-in/check-out and Project Leader attendance correction.

## 37.1 Supported check-in methods

- QR code at project site;
- QR code displayed on Project Leader’s device;
- GPS/location proximity;
- QR + GPS combination.

Continuous volunteer location tracking is not required.

Location should be requested only as needed for check-in/out.

## 37.2 Attendance status

Project Leader may confirm/correct:

- present;
- late;
- absent;
- check-in;
- check-out;
- service duration.

HAM calculates volunteer service hours from check-in/out where possible.

---

# 38. Project-Day Safety

Project Leader completes a very short safety checklist before volunteer check-in/work begins.

Required confirmations:

- known site hazards reviewed;
- required PPE addressed;
- emergency process/contact understood;
- Task Leaders briefed.

A full tool/material inventory confirmation is not required before moving to In Progress.

After the checklist is complete and work begins, the Project Leader may set project status to In Progress.

---

# 39. Site Hazards and Safety Holds

Requester must disclose known hazards such as:

- aggressive animals;
- mold;
- exposed wiring;
- structural instability;
- pests;
- comparable hazards.

Serious disclosed or discovered hazards may place a project On Hold automatically.

Hold remains until sufficiently addressed.

HAM Director or Assistant Director may clear the safety hold.

A written justification is not required for clearing the hold.

---

# 40. Contractors and Professionals

Professional services may be represented as:

- vendor/expense only; or
- limited HAM participant account.

Project-specific professional accounts may access only the projects/tasks to which they are assigned.

When assigned, they may receive necessary:

- project address;
- requester contact information;
- task details.

They do not receive unrelated project access.

## 40.1 Requirements

Contractor/professional must:

- accept HAM contractor/service terms;
- maintain their own liability insurance.

HAM does not require uploading the insurance policy.

Project Leader/Manager records a simple:

**Liability insurance verified: Yes / No**

A professional cannot begin work unless verification is Yes.

---

# 41. Homeowner Service Agreement

Requester/homeowner must accept HAM’s service/liability agreement before work begins.

Supported forms:

- electronic signing;
- offline/manual signing.

If signed offline:

- photo or PDF of signed agreement must be uploaded.

The signed agreement is stored only inside HAM, not Google Drive.

Retention: seven years.

The system must retain:

- exact agreement version;
- signature;
- date/time;
- acceptance evidence.

If the agreement changes before the project occurs, the requester must accept the current version before work begins.

---

# 42. Volunteer Onboarding Requirements

Before becoming eligible to participate, a volunteer must complete:

- HAM profile;
- required contact information;
- media release;
- liability waiver;
- safety agreement;
- emergency contact.

Agreement records retain:

- agreement version;
- acceptance timestamp;
- signature/evidence.

Retention: seven years after volunteer becomes inactive.

When a required agreement changes, active volunteers must accept the new version before participating again.

---

# 43. Volunteer Media Release

Media release is mandatory for HAM participation.

If a volunteer does not accept the media release, they cannot participate.

If a volunteer later withdraws consent:

- volunteer status becomes inactive;
- they cannot participate until consent is restored.

This replaces the earlier concept of participating while opting out of public media.

---

# 44. Background Checks

SDA/Adventist background-check integration is explicitly deferred to Version 2.

HAM V1 shall contain no background-check status field and shall not block V1 implementation on background-check integration.

Future Version 2 may integrate with Adventist Screening Verification / Sterling Volunteers.

---

# 45. Requester Media Uploads

Before uploading media, requester must verify ownership of either their email or mobile number.

Initial upload allowance:

- maximum 10 photos;
- maximum 3 videos;
- maximum video duration: 2 minutes each.

HAM automatically compresses/optimizes all uploads.

Only compressed/optimized media is retained.

Original media is discarded after successful processing.

---

# 46. Additional Media Requests

Authorized users may reopen requester media upload:

- HAM Director;
- Assistant Directors;
- Project Leader;
- pastors;
- Board representative.

Each reopening creates another batch allowance:

- 10 photos;
- 3 videos;
- 2-minute maximum per video.

Each additional batch records:

- who requested it;
- reason;
- upload timestamp.

---

# 47. Media Retention

## 47.1 Videos

Standard project video retention:

30 days after project Completed or Rejected.

## 47.2 Photos

Standard project photo retention:

90 days after project Completed or Rejected.

## 47.3 Future Google Drive behavior

When Drive integration is enabled, retention applies to:

- HAM storage;
- Google Drive.

Media should be deleted from both locations after retention expires.

## 47.4 Publication exception

Media explicitly approved for church/public communications may be exempt from standard deletion.

Authorized publication approvers:

- Social Media Specialist;
- HAM Director;
- pastors.

Long-term media follows a separate communications retention policy.

---

# 48. Media Consent

Public use requires requester/homeowner consent.

Consent is:

- project-specific;
- media-item-specific.

Requester may independently approve or deny:

- individual photos;
- individual videos;
- internal church use;
- public/social-media use.

Media involving minors requires separate parent/legal-guardian consent for public use.

Leadership approval alone does not override homeowner or guardian consent.

---

# 49. Social Media Specialist Access

Social Media Specialist should receive only the project/media information needed for communication duties.

The role should support:

- mobile upload;
- media review;
- consent status;
- publication approval status;
- media categorization.

Sensitive project information should not be exposed unless operationally required.

---

# 50. Google Drive Integration

Google Drive integration is deferred until shortly after V1.

V1 uses internal media storage.

The architecture must support later automatic copying of media into Google Drive.

Drive must not become a dependency for normal V1 project operations.

---

# 51. Google Calendar Integration

Google Calendar integration is part of V1.

HAM will use the church’s existing **Men’s Ministry Google Calendar**.

Calendar is restricted to leadership.

Authorized calendar audience:

- HAM Director;
- Assistant Directors;
- Project Leaders;
- pastors;
- Board representative;
- Administrator.

Volunteers, requesters, and contractors are not added as calendar guests.

They receive HAM notifications instead.

## 51.1 Calendar privacy

Calendar titles must be privacy-conscious.

Example:

**HAM Project #024 — Plumbing Repair**

Calendar must not expose:

- requester name;
- requester personal circumstances;
- project address.

Sensitive information remains inside HAM.

## 51.2 Calendar events

A confirmed project creates an event.

Multiple distinct work dates may create separate events.

Task-specific events are created only when tasks occur at meaningfully different dates/times.

HAM schedule changes synchronize to the linked Google Calendar event.

---

# 52. Project Status Lifecycle

Recommended V1 lifecycle:

Submitted  
→ Awaiting Approval  
→ Approved  
→ Assessment Required  
→ Assessment Completed  
→ Planning  
→ Recruiting  
→ Ready  
→ Scheduled  
→ In Progress  
→ Completed – Follow-Up Required  
→ Completed

Alternate states:

- Rejected;
- Reconsideration Pending;
- On Hold;
- Cancelled;
- Not Executable.

Urgent is an attribute/priority designation rather than a separate lifecycle.

---

# 53. Project Completion

Project may be marked Completed by:

- Project Leader;
- HAM Director;
- Assistant Director.

A project can complete with unresolved follow-up tasks.

In that case:

**Completed – Follow-Up Required**

Follow-up tasks may be completed or cancelled by:

- original Task Leader;
- Project Leader;
- HAM Director;
- Assistant Director.

Cancelled follow-up tasks require a short reason.

When every follow-up task is either Completed or Cancelled, HAM automatically changes:

**Completed – Follow-Up Required → Completed**

---

# 54. Completion Survey

When project reaches Completed, requester immediately receives a survey.

Survey includes:

- 1–5 satisfaction rating;
- whether the primary need was addressed;
- optional comments.

Survey does not create additional work requests.

Additional needs require a new HAM request.

Requester may complete survey without an account using a secure one-time link.

Survey link expires after 30 days.

If not completed, one reminder is sent seven days after completion.

Survey visibility:

- HAM Director;
- Assistant Directors;
- Project Leader;
- pastors;
- Board representative.

Aggregate reporting uses anonymous comments by default.

Authorized project viewers may see comments attached to the project record.

---

# 55. Volunteer Post-Project Feedback

Volunteers receive a short post-project feedback form.

Suggested topics:

- what went well;
- issues;
- suggestions.

Feedback is not anonymous.

It is visible only to:

- submitting volunteer;
- HAM Director;
- Assistant Directors.

Project Leader does not see volunteer feedback.

This supports the ministry’s accountability principle: users remain accountable for their words and actions.

---

# 56. Incident Reporting

Any volunteer, Project Leader, HAM Director, or Assistant Director may submit an incident report.

Incident categories may include:

- injury;
- property damage;
- safety issue;
- emergency-services involvement;
- other significant event.

Every incident immediately notifies:

- HAM Director;
- Assistant Directors.

Serious incidents also automatically notify pastoral staff.

A pastor decides whether the Board representative should be notified.

Incident reports become immutable after submission.

Corrections are added as dated amendments.

Original report remains preserved.

Retention: seven years.

---

# 57. Comments and Accountability

Users may:

- create comments;
- delete their own comments.

Users may not edit submitted comments.

A user who wants to change a comment must:

- delete it;
- submit a new comment.

Normal users do not see deleted comments.

Audit record retains:

- deleted content;
- author;
- deleter;
- deletion timestamp.

Deleted content is visible only to:

- Administrator;
- HAM Director.

Deleted comments cannot be restored to normal view.

---

# 58. Audit Log

Meaningful actions must be logged.

Examples:

- approvals;
- rejections;
- reconsiderations;
- status changes;
- permission changes;
- role changes;
- admin overrides;
- dependency overrides;
- assignment changes;
- budget changes;
- comment deletion;
- requester access regeneration;
- impersonation;
- incident actions.

Audit retention: one year.

Administrator and HAM Director may export audit logs.

Supported export:

- CSV/Excel;
- PDF.

Filtering:

- date range;
- user;
- project;
- action type;
- role.

---

# 59. Administrator Impersonation

Administrator may impersonate another user for troubleshooting.

Impersonation allows operational actions on the user’s behalf.

Audit must show both identities:

> Administrator A acting as Volunteer B.

Before impersonation:

- administrator must enter reason.

Session expires after 15 minutes of inactivity.

Sensitive privileged actions are blocked while impersonating.

Examples:

- role changes;
- permission changes;
- privileged budget approvals;
- protected administrative actions.

Administrator must return to their own identity to perform those actions.

---

# 60. Authentication and MFA

## 60.1 Privileged leadership

Mandatory MFA for:

- Administrator;
- HAM Director;
- Assistant Directors;
- pastors;
- Board representative.

Project Leaders do not require MFA solely because of Project Leader status.

## 60.2 Volunteers

May use passwordless authentication such as:

- email magic link;
- SMS one-time code where supported.

## 60.3 Requesters

Use secure request-specific links rather than persistent HAM accounts.

---

# 61. AI Assistant — V1

V1 includes limited, advisory AI.

AI is intended primarily to reduce workload for:

- HAM Director;
- Assistant Directors;
- Project Leaders;
- Administrator.

AI output is always a suggestion/draft until accepted by an authorized human.

## 61.1 V1 AI capabilities

AI may:

- draft project plans from request + assessment;
- suggest tasks;
- suggest materials;
- suggest tools;
- suggest volunteer counts;
- suggest skill requirements;
- suggest similar historical projects;
- suggest approved templates;
- draft budget estimates;
- suggest volunteer teams;
- suggest project schedules;
- draft communications;
- summarize project status;
- generate completion reports;
- suggest cost-saving alternatives.

## 61.2 AI staffing support

AI may consider:

- skills;
- tools;
- availability;
- travel;
- reliability;
- mentor status;
- credentials.

AI does not directly override volunteer eligibility rules.

## 61.3 AI budget support

AI may use:

- current task structure;
- materials;
- rentals;
- outside services;
- contingency;
- comparable prior projects.

AI-generated costs must be identified as estimates.

## 61.4 AI guardrails

AI cannot independently:

- approve projects;
- reject projects;
- redefine scope;
- approve financial increases;
- bypass legal licensing requirements;
- bypass safety restrictions;
- publish media;
- assign privileged roles;
- change permissions.

All consequential AI output requires human review.

---

# 62. Advanced AI — Later Phase

Deferred AI capabilities may include:

- proactive cross-project risk analysis;
- schedule optimization;
- advanced cost optimization;
- predictive volunteer shortages;
- deeper project analytics;
- automated operational recommendations.

These are not required for initial V1 launch.

---

# 63. Dashboard and Balanced Scorecard

HAM should provide a well-designed ministry dashboard.

The member-facing scoreboard emphasizes:

1. Families Served
2. Volunteer Hours

Balanced supporting measures:

- Projects Completed;
- Active Volunteers;
- Satisfaction Rating;
- Estimated Value / Cost of Assistance.

Time views:

- This Month;
- This Year;
- All-Time.

No private requester or volunteer information should appear on member-facing scoreboards.

Leadership dashboards may contain operational detail appropriate to role.

---

# 64. Leadership Dashboard

Recommended leadership dashboard areas:

- requests awaiting approval;
- approved requests awaiting assessment;
- projects in planning;
- projects needing volunteers;
- projects with missing qualifications;
- upcoming projects;
- reconfirmation problems;
- blocked tasks;
- projects on hold;
- credential alerts;
- budget risks;
- incidents;
- follow-up projects;
- recent completions.

AI may provide a concise “What needs attention” summary.

---

# 65. Post-Project Report

AI generates a draft post-project summary when a project completes.

Recommended content:

- project identifier;
- service category;
- tasks completed;
- tasks cancelled;
- volunteer count;
- volunteer hours;
- budget estimate;
- actual cost;
- requester/church contribution summary;
- incidents;
- follow-up status;
- media status;
- requester satisfaction score.

Sensitive personal information should be excluded from aggregate ministry reports.

---

# 66. Data Model — Core Entities

Implementation should include at minimum:

### Identity
- User
- Role
- Permission
- SharedIdentityProfile
- HAMVolunteerProfile

### Request
- AssistanceRequest
- Requester
- Property
- RequestContactVerification
- RequestMedia
- Approval
- Reconsideration

### Project
- Project
- SiteAssessment
- ProjectScope
- ProjectHold
- ProjectSchedule
- ProjectLeaderAssignment

### Task
- Task
- TaskDependency
- TaskLeaderAssignment
- TaskRequirement
- TaskTemplate

### Volunteer
- VolunteerSkill
- ObservedSkill
- LearningInterest
- VolunteerTool
- VolunteerAvailability
- TravelPreference
- Credential
- MentorDesignation

### Staffing
- VolunteerInvitation
- Assignment
- WaitlistEntry
- Reconfirmation
- Cancellation
- ExcusedEvent
- Attendance
- ServiceHours

### Finance
- ProjectBudget
- BudgetLine
- FundingParty
- CostChangeApproval

### Compliance
- Agreement
- AgreementVersion
- AgreementAcceptance
- ContractorVerification
- MediaConsent

### Operations
- Comment
- Notification
- Incident
- IncidentAmendment
- AuditEvent

### Feedback
- RequesterSurvey
- VolunteerFeedback

### Integration
- CalendarEventReference
- ExternalIntegrationEvent
- FutureFitnessIntegrationReference
- FutureDriveMediaReference

---

# 67. Permission Principles

## Administrator

Full system configuration and user-management access, subject to immutable/protected historical rules.

## HAM Director

Full ministry-operational access including:

- scope;
- projects;
- volunteer management;
- planning;
- audit viewing;
- deleted-comment audit access.

## Assistant Director

Broad operational rights but cannot independently redefine project scope.

## Project Leader

Project-specific execution authority.

## Task Leader

Task-specific operational authority.

## Pastor

Approval, urgent certification, relevant project oversight.

## Board Representative

Records Board decisions and accesses information required for Board responsibilities.

## Social Media Specialist

Media-focused access only.

## Volunteer

Own profile, assigned/invited projects, attendance, feedback, commitments.

## Contractor

Assigned project/task only.

## Requester

Request-specific secure portal only.

---

# 68. Privacy Requirements

HAM must follow least-privilege access.

Sensitive information includes:

- requester identity;
- service address;
- household circumstances;
- contact details;
- financial assistance information;
- incident reports;
- agreement documents.

External integrations must receive only necessary data.

Calendar must not contain:

- requester name;
- address;
- sensitive household details.

Public/member dashboards must contain aggregates only.

---

# 69. Media and File Security

Uploads must:

- validate file type;
- scan where technically appropriate;
- enforce size limits;
- compress automatically;
- use randomized/non-guessable storage identifiers;
- require authorization to retrieve.

Request-media access is project-scoped.

Signed legal/service agreements must be access-controlled separately from ordinary media.

---

# 70. Non-Functional Requirements

## 70.1 Responsive design

HAM must work well on:

- phone;
- tablet;
- desktop.

Mobile usability is essential for:

- assessment;
- project execution;
- attendance;
- photos;
- volunteer responses.

## 70.2 Performance

Typical interactive pages should target fast perceived response.

Core project/request pages should normally load within approximately 2 seconds under expected church-scale usage.

## 70.3 Availability

HAM should tolerate third-party integration outages.

Failure of:

- Google Calendar;
- future Google Drive;
- future Fitness & Accountability;
- credential verification provider

must not corrupt project data.

## 70.4 Accessibility

Although formal multilingual support is deferred, interfaces should follow accessible web design and target WCAG 2.2 AA where reasonably practical.

## 70.5 Time zone

All stored timestamps should use UTC internally with correct local-time presentation.

## 70.6 Auditability

Consequential actions must have reliable actor and timestamp attribution.

---

# 71. Search

Authorized HAM users should be able to search/filter by:

- project/request ID;
- requester;
- address where authorized;
- status;
- project category;
- volunteer;
- skill;
- date;
- leader;
- task;
- urgency.

Duplicate detection should leverage prior request/project data.

---

# 72. Reporting

Core V1 reports should include:

- families served;
- volunteer hours;
- projects completed;
- active volunteers;
- satisfaction;
- estimated/actual project cost;
- requester contribution;
- church contribution;
- volunteer participation;
- cancellations/no-shows;
- project turnaround time.

Exports should be available where operationally useful.

---

# 73. V1 Scope

V1 SHALL include:

- public/church-link request intake;
- requester verification;
- request media;
- approval/rejection/reconsideration;
- urgent approvals;
- mandatory site assessment;
- project planning;
- task management;
- simple project budgets;
- volunteer profiles;
- skills;
- learning interests;
- mentors;
- tools;
- availability;
- travel preference;
- credential tracking/verification architecture;
- automated volunteer matching;
- invitations;
- waitlists;
- reconfirmation;
- reliability scoring;
- attendance;
- QR/GPS check-in/check-out;
- service hours;
- safety checklist;
- holds;
- incidents;
- agreements;
- contractor participation;
- media consent;
- internal media storage;
- project completion;
- follow-up tasks;
- requester surveys;
- volunteer feedback;
- audit logs;
- administrator controls;
- impersonation;
- MFA for privileged leadership;
- limited advisory AI;
- balanced-scorecard dashboard;
- Google Calendar integration;
- integration-ready APIs/events.

---

# 74. Deferred Beyond V1

## Shortly after V1

Google Drive media integration.

## Version 2

- Fitness & Accountability integration;
- SMS through Fitness & Accountability;
- SDA/Adventist background-check integration;
- additional AI automation;
- potentially broader reporting/analytics.

## Future

- multilingual support;
- multi-campus/multi-church support;
- church member-management integration;
- more advanced predictive AI.

---

# 75. Explicit V1 Non-Goals

V1 does not require:

- church-owned tool inventory;
- multi-campus support;
- Spanish/multilingual UI;
- background-check integration;
- direct HAM SMS infrastructure;
- Google Drive dependency;
- separate requester account system;
- full accounting software functionality;
- continuous GPS tracking;
- fully autonomous AI;
- automated Board budget approval workflow.

---

# 76. Key Automation Rules

HAM should automate where rules are deterministic.

Examples:

- auto-promote qualified waitlisted volunteer;
- auto-release unconfirmed slot five days before project;
- auto-stop waitlist cycling at 48 hours;
- auto-transition Follow-Up Required → Completed;
- auto-send completion survey;
- auto-send seven-day survey reminder;
- auto-calculate volunteer hours;
- auto-flag expiring credentials;
- auto-flag duplicates;
- auto-enforce media retention;
- auto-log administrative events;
- auto-sync calendar changes;
- auto-invalidate old requester access links.

---

# 77. Core Acceptance Criteria

V1 should not be considered production-ready until the following end-to-end scenario succeeds:

1. A non-member requester opens the public form.
2. Requester verifies email or mobile.
3. Requester submits a legitimate assistance request with photos/video.
4. A pastor or Board route approves it.
5. HAM schedules and completes mandatory site assessment.
6. Assessment identifies skills, tools, materials, safety, cost, and scope.
7. HAM Director approves/refines scope.
8. AI prepares a draft plan.
9. Leadership accepts/modifies tasks and budget.
10. System identifies qualified volunteers.
11. Invitations are sent automatically.
12. Volunteers accept first-come/first-served.
13. Excess qualified volunteers enter waitlist.
14. Volunteer reconfirmation occurs seven days before service.
15. Staffing gaps are handled correctly.
16. Leadership calendar receives privacy-conscious project event.
17. Project Leader completes short safety checklist.
18. Volunteers check in by QR and/or location.
19. Tasks progress through execution.
20. Attendance/service hours are captured.
21. Unexpected work can be documented safely.
22. Incident workflow works if required.
23. Project can complete with follow-up tasks.
24. Final follow-up completion automatically closes project.
25. Requester immediately receives survey.
26. Volunteer feedback is privately captured.
27. Balanced scorecard updates families served and volunteer hours.
28. Audit records identify every consequential actor.
29. AI generates post-project report.
30. Privacy restrictions prevent unauthorized exposure throughout.

---

# 78. Suggested Technical Architecture

The specific technology stack remains implementation-defined, but the logical architecture should contain:

### Front End
Responsive web application / PWA-style experience.

### Backend API
Domain-oriented application API.

### Authentication
Shared identity architecture capable of later serving both HAM and Fitness & Accountability.

### Database
Relational database strongly recommended because HAM contains substantial relationships, workflows, permissions, assignments, and audit data.

### Object Storage
Private storage for:

- compressed images;
- compressed video;
- signed documents.

### Notification Service
Email + in-app in V1.

Designed for later Fitness/SMS integration.

### AI Service Layer
AI calls must pass through a controlled HAM service layer rather than giving the model unrestricted application/database access.

### Integration Layer
Adapters/events for:

- Google Calendar;
- future Google Drive;
- future Fitness & Accountability;
- credential-verification sources.

### Audit Service
Central event logging.

### Background Jobs
Used for:

- notifications;
- reminder schedules;
- media retention;
- credential alerts;
- waitlist promotion;
- survey reminders;
- calendar synchronization.

---

# 79. AI Technical Guardrail

AI should never directly write consequential state changes into production records without application-level authorization.

Preferred flow:

AI Suggestion  
→ User Reviews  
→ User Accepts  
→ HAM Validates Permissions/Rules  
→ HAM Writes Transaction  
→ Audit Event Recorded

This ensures AI cannot bypass:

- permissions;
- legal credentials;
- safety controls;
- financial rules;
- human approval.

---

# 80. Product Success Criteria

HAM succeeds when:

- legitimate needs move from request to service faster;
- volunteer leaders spend less time coordinating manually;
- volunteers are appropriately matched;
- commitment/no-show visibility improves;
- volunteer hours are accurately measured;
- project costs are understandable;
- leaders can quickly see what needs attention;
- requesters receive clear, compassionate communication;
- household privacy is protected;
- ministry leadership can quantify impact;
- the application remains simple enough that volunteers actually use it.

The two most important ministry-level indicators are:

**Families Served**  
and  
**Volunteer Hours**

These should remain the primary metrics on HAM’s balanced-scorecard dashboard.

---

# 81. Final V1 Product Definition

HAM V1 is a privacy-conscious, accountability-driven, AI-assisted ministry operations platform that enables a volunteer-led church ministry to receive legitimate home-assistance requests, obtain pastoral/Board approval, assess and plan work, manage simple budgets, match qualified volunteers, schedule and execute projects safely, measure participation and impact, and maintain clear accountability from request through completion.

The system should automate administrative work aggressively where rules are clear, while reserving ministry judgment, project scope, safety, financial commitment, and consequential decisions for authorized people.
