# HAM permission matrix

Generated from `ham/authz/matrix.py` — the single source of truth (PRD §67, §68, Q-038: fixed
in code, never Admin-editable). Do not hand-edit this file; run
`python manage.py build_permission_matrix` after changing the matrix, and
`python manage.py build_permission_matrix --check` fails CI if this file is stale.

SU = requires a fresh step-up (Q-010, Q-031, Q-046). IB = refused while impersonating (§59).

| Action | Allowed roles | Scope | SU | IB | PRD |
|---|---|---|---|---|---|
| `audit.export` | Administrator, HAM Director | any | SU | IB | §58, Q-010 |
| `audit.view` | Administrator, HAM Director | any |  |  | §58, §67, Q-021 |
| `audit.view_deleted_comment` | Administrator, HAM Director | any |  | IB | §57 |
| `church_profile.update` | Administrator | any |  | IB | §4.11, Q-007 |
| `impersonation.start` | Administrator | any | SU | IB | §59, Q-034 |
| `impersonation.stop` | _(none yet)_ | impersonating_admin |  |  | §59 |
| `intake_source.manage` | Assistant Director, HAM Director | any |  |  | §6, Q-106 |
| `integrations.view_status` | Administrator | any |  |  | §4.11 |
| `leader.project.assign` | Assistant Director, HAM Director | any |  | IB | §16, Q-031, Q-054 |
| `leader.project.revoke` | Assistant Director, HAM Director | any |  | IB | §16, Q-031, Q-054 |
| `leader.task.assign` | Assistant Director, HAM Director | any |  | IB | §17, Q-031, Q-054 |
| `leader.task.revoke` | Assistant Director, HAM Director | any |  | IB | §17, Q-031, Q-054 |
| `me.recovery_codes.regenerate` | Administrator, Assistant Director, Board representative, Contractor, HAM Director, Pastor, Project Leader, Social Media Specialist, Task Leader, Volunteer | self | SU | IB | §60.1, Q-046 |
| `me.security.manage` | Administrator, Assistant Director, Board representative, Contractor, HAM Director, Pastor, Project Leader, Social Media Specialist, Task Leader, Volunteer | self |  | IB | §60 |
| `me.sign_in_email.change` | Administrator, Assistant Director, Board representative, Contractor, HAM Director, Pastor, Project Leader, Social Media Specialist, Task Leader, Volunteer | self | SU | IB | §60.2, Q-051, Q-046 |
| `me.update` | Administrator, Assistant Director, Board representative, Contractor, HAM Director, Pastor, Project Leader, Social Media Specialist, Task Leader, Volunteer | self |  | IB | §67, §59 |
| `me.view` | Administrator, Assistant Director, Board representative, Contractor, HAM Director, Pastor, Project Leader, Social Media Specialist, Task Leader, Volunteer | self |  |  | §67 |
| `notification.acknowledge` | Administrator, Assistant Director, Board representative, Contractor, HAM Director, Pastor, Project Leader, Social Media Specialist, Task Leader, Volunteer | self |  | IB | §10, §35 |
| `outbox.retry` | Administrator | any |  | IB | §70.3 |
| `request.approve` | Board representative, Pastor | any |  | IB | §4.2, §4.3, §8, §10, §67, Q-048, Q-153 |
| `request.cancel` | Assistant Director, HAM Director | any |  | IB | §52, Q-107, Q-111 |
| `request.category.change` | Assistant Director, HAM Director | any |  |  | Q-109 |
| `request.contact_verify_phone` | Assistant Director, HAM Director | any |  | IB | Q-025 |
| `request.decision.record_phoned` | Assistant Director, HAM Director | any |  | IB | §8.3, Q-025, Q-159 |
| `request.decision.undo` | Board representative, Pastor | any |  | IB | §8, §3.3, §58, Q-156, Q-176 |
| `request.history.view` | Assistant Director, Board representative, HAM Director, Pastor | any |  |  | §5, §9 |
| `request.list` | Administrator, Assistant Director, Board representative, HAM Director, Pastor | any |  |  | §8, §64, Q-106 |
| `request.needs_phone_check.list` | Assistant Director, HAM Director | any |  |  | Q-025 |
| `request.question.ask` | Assistant Director, Board representative, HAM Director, Pastor | any |  | IB | §7.2, Q-162 |
| `request.question.record_answer` | Assistant Director, Board representative, HAM Director, Pastor | any |  | IB | §7.2, Q-162 |
| `request.question.withdraw` | Assistant Director, Board representative, HAM Director, Pastor | any |  | IB | §7.2, Q-162 |
| `request.reconsideration.decide` | Board representative, Pastor | any |  | IB | §8.4, Q-048, Q-157 |
| `request.reconsideration.record_phone` | Assistant Director, HAM Director | any |  | IB | §8.4, Q-025, Q-159 |
| `request.reject` | Board representative, Pastor | any |  | IB | §8.3, Q-048, Q-154 |
| `request.submit` | REQUESTER | any |  |  | §6, §7.1, Q-100 |
| `request.urgency.review` | Pastor | any |  | IB | §10, §67, Q-048, Q-160 |
| `request.view` | Administrator, Assistant Director, Board representative, HAM Director, Pastor | any |  |  | §8, §67, Q-124 |
| `request_media.reopen` | Assistant Director, Board representative, HAM Director, Pastor | any |  |  | §46 |
| `request_media.view` | Administrator, Assistant Director, Board representative, HAM Director, Pastor | any |  |  | §69, Q-124 |
| `requester.media.remove` | REQUESTER | own_request |  |  | §45, Q-118 |
| `requester.media.upload` | REQUESTER | own_request |  |  | §7.1, §45, Q-118 |
| `requester.question.answer` | REQUESTER | own_request |  |  | §7.2, Q-162 |
| `requester.reconsideration.request` | REQUESTER | own_request |  |  | §8.3, §8.4, Q-155, Q-158 |
| `requester.request.view` | REQUESTER | own_request |  |  | §7.2, §67, Q-101 |
| `requester_link.regenerate` | REQUESTER | own_request |  |  | §7.3, §58, Q-116, Q-117 |
| `requester_pii.reveal` | Assistant Director, Board representative, HAM Director, Pastor | any |  |  | §67, §68, Q-009, Q-024, Q-081, Q-122, Q-125 |
| `role.grant_global` | Administrator, HAM Director | any | SU | IB | §4.11, §58, Q-041 |
| `role.revoke_global` | Administrator, HAM Director | any | SU | IB | §4.11, §58, Q-041 |
| `rules.view` | Administrator, HAM Director | any |  |  | §4.11 |
| `shell.use` | Administrator, Assistant Director, Board representative, Contractor, HAM Director, Pastor, Project Leader, Social Media Specialist, Task Leader, Volunteer | any |  |  | §67 |
| `system.intake.purge` | SYSTEM | any |  |  | §76 |
| `system.media.process` | SYSTEM | any |  |  | §45 |
| `system.media.purge` | SYSTEM | any |  |  | §47 |
| `system.request.complete_intake_checks` | SYSTEM | any |  |  | §9 |
| `system.request.finalize_rejection` | SYSTEM | any |  |  | §8.4, Q-155 |
| `user.disable` | Administrator, HAM Director | any |  | IB | §4.11, Q-035, Q-052, Q-079 |
| `user.enable` | Administrator, HAM Director | any |  | IB | §4.11, Q-052, Q-079 |
| `user.invitation_cancel` | Administrator, Assistant Director, HAM Director | any |  | IB | §4.11, Q-037, Q-052 |
| `user.invitation_resend` | Administrator, Assistant Director, HAM Director | any |  | IB | §4.11, Q-037, Q-071 |
| `user.invite` | Administrator, Assistant Director, HAM Director | any |  | IB | §4.11, Q-037 |
| `user.list` | Administrator, HAM Director | any |  |  | §4.11, Q-041 |
| `user.mfa_reset` | Administrator | any | SU | IB | §60.1, Q-035 |
| `user.update_identity` | Administrator | any |  |  | §4.11 |
| `user.view` | Administrator, HAM Director | any |  |  | §4.11, Q-041 |
