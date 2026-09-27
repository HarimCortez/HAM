# HAM PRD — Open Questions

Decisions the PRD leaves open. Agents add rows; the product owner decides.
Code that depends on an open item is marked `// PRD-GAP Q-NNN`.

| ID | PRD § | Question | Options | Proposed default | Status / Decision |
|---|---|---|---|---|---|
| Q-001 | §34.1 | Exact reliability penalty numbers (small / moderate / larger / major / largest) and recovery rate | Various | To be proposed by ham-rules-engineer | Open |
| Q-002 | §28 | Invitation response deadline length | e.g. 24h / 48h / 72h | 48h | Open |
| Q-003 | §78 | Technology stack and hosting | See ADR 0001 | To be drafted by ham-architect | Open |
| Q-004 | §28, §40, §67 | What location detail do volunteers see, and when? | Area only / area on invite + full address once Assigned / full address on invite | Area + distance on invite; full address once Assigned; never requester name, phone or circumstances | Open |
| Q-005 | §63, §68 | May the member scoreboard (aggregates only) also be embedded publicly on the church website? | Signed-in only / also public embed | Signed-in HAM users only in V1 | Open |
| Q-006 | §37, §70.3 | Can volunteers check in while offline? | Online only / queue with device time and sync later | Queue with "pending sync"; Project Leader can correct (§37.2) | Open |
| Q-007 | §7.2 | How does a requester contact HAM from the secure page? | Ministry phone/email shown / in-app messages / nothing | Show an admin-configured ministry phone and email | Open |
| Q-008 | §13, §7.2 | How does a requester approve an increase in their cost share? (Who approves is settled by §13.) | Card on secure page / leader records offline approval / both | Both, each audited | Open |
| Q-009 | §16, §17, §67 | Which requester details do Project and Task Leaders see? | Various | PL: name, address, phone, hazards; TL: address + hazards | Open |
| Q-010 | §60.1 | How often are MFA users re-challenged on a trusted device? | Every sign-in / remember 30 days / sensitive actions only | Remember 30 days; re-check for audit export and role changes | Open |
| Q-011 | §32 | Reminder cadence between day 7 and day 5 before a project | Daily / once at day 6 | Daily; values in the rules module | Open |
| Q-012 | §63 | What does "Cost of Assistance / Estimated Value" include? | Actual cost / cost + volunteer hours × rate / both | Actual cost, labelled "Cost of Assistance" | Open |
| Q-013 | §29, §30, §64 | When does an understaffed project start alerting leadership? | 96 h / 72 h / at 7-day reconfirmation | 96 h before start; rules module | Open |
| Q-014 | §20, §42 | When an agreement changes, what happens to a volunteer's held future slots? (Re-acceptance itself is settled by §42.) | Keep and block check-in / release slot | Keep; block check-in until accepted; alert leader 48 h before | Open |
| Q-015 | §64 | What counts as a "budget risk"? | Actual > estimate by X% / > estimate + contingency / leader flags | Actual over estimate + contingency; rules module | Open |
| Q-016 | §70.4 | Is a dark theme in V1 scope? | Light only / follow device setting / device setting + in-app choice | Light only in V1; tokens keep dark values for later | Open |
| Q-017 | §28–§33 | Invitation and commitment state names (PRD names only Pending Confirmation and waitlist) | Accept proposal / name in PRD | Invited, Accepted, Declined, No Response, Waitlisted, Pending Confirmation, Confirmed, Reconfirmation Needed, Released, Cancelled, No-Show | Open |
| Q-018 | §24 | Credential verification status values; is expiry separate? | Separate fields / one combined list | Unverified / Verified / Could Not Verify; expiry computed from the date ("Expiring Soon" is a badge) | Open |
| Q-019 | §7.1, §60.2, §75 | Verification allows "SMS one-time code" but V1 excludes HAM SMS infrastructure | Email only in V1 / SMS provider for codes only | Email only in V1 | Open |
| Q-020 | §37.2 | What counts as "Late"? | Any time after start / after a grace period / leader judgment | After a 15-min grace period in the rules module | Open |
| Q-021 | §58, §67 | Can Project Leaders see a per-project activity history? | No / read-only non-sensitive events on their projects | No | Open |
| Q-022 | §33 | Is "Excused" a flag on a cancellation/no-show or its own status? | Flag + reason / status | Flag + reason | Open |
| Q-023 | §16, §67, §68 | Can assigned volunteers see and call the Project Leader's phone number from the project-day card? | Yes, for assigned volunteers on project day / no, in-app only | Yes, for assigned volunteers only, project day and the day before | Open |
| Q-024 | §58, §68 | Should viewing a requester's name or address on leadership screens (hover card or side panel) create an audit event? | Display only / log each reveal | Display only for the Director; log reveals by other roles | Open |

## Owner action items (not PRD questions)
- Confirm Miami Temple communications approves HAM's use of the church logo files in `design-system/assets/`, and ask whether a brand guide exists.
