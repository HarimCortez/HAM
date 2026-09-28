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
| `outbox.retry` | Administrator | any |  | IB | §70.3 |
| `requester_pii.reveal` | _(none yet)_ | any |  |  | §67, §68, Q-009, Q-024 |
| `role.grant_global` | Administrator, HAM Director | any | SU | IB | §4.11, §58, Q-041 |
| `role.revoke_global` | Administrator, HAM Director | any | SU | IB | §4.11, §58, Q-041 |
| `rules.view` | Administrator, HAM Director | any |  |  | §4.11 |
| `shell.use` | Administrator, Assistant Director, Board representative, Contractor, HAM Director, Pastor, Project Leader, Social Media Specialist, Task Leader, Volunteer | any |  |  | §67 |
| `user.disable` | Administrator, HAM Director | any |  | IB | §4.11, Q-035, Q-052, Q-079 |
| `user.enable` | Administrator, HAM Director | any |  | IB | §4.11, Q-052, Q-079 |
| `user.invitation_cancel` | Administrator, Assistant Director, HAM Director | any |  | IB | §4.11, Q-037, Q-052 |
| `user.invitation_resend` | Administrator, Assistant Director, HAM Director | any |  | IB | §4.11, Q-037, Q-071 |
| `user.invite` | Administrator, Assistant Director, HAM Director | any |  | IB | §4.11, Q-037 |
| `user.list` | Administrator, HAM Director | any |  |  | §4.11, Q-041 |
| `user.mfa_reset` | Administrator | any | SU | IB | §60.1, Q-035 |
| `user.update_identity` | Administrator | any |  |  | §4.11 |
| `user.view` | Administrator, HAM Director | any |  |  | §4.11, Q-041 |
