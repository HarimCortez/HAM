"""Role codes (foundation.md §3 "RoleAssignment"). Pure data, no Django.

``ham.identity.models.RoleAssignment.role`` choices are built from these constants (identity
depends on authz, never the reverse — foundation.md §1 dependency rules).
"""

from __future__ import annotations

ADMINISTRATOR = "ADMINISTRATOR"
HAM_DIRECTOR = "HAM_DIRECTOR"
ASSISTANT_DIRECTOR = "ASSISTANT_DIRECTOR"
PASTOR = "PASTOR"
BOARD_REPRESENTATIVE = "BOARD_REPRESENTATIVE"
SOCIAL_MEDIA_SPECIALIST = "SOCIAL_MEDIA_SPECIALIST"
VOLUNTEER = "VOLUNTEER"
CONTRACTOR = "CONTRACTOR"
PROJECT_LEADER = "PROJECT_LEADER"
TASK_LEADER = "TASK_LEADER"

# Global roles: scope_type is always null (foundation.md §3 RoleAssignment invariants).
GLOBAL_ROLES: frozenset[str] = frozenset(
    {
        ADMINISTRATOR,
        HAM_DIRECTOR,
        ASSISTANT_DIRECTOR,
        PASTOR,
        BOARD_REPRESENTATIVE,
        SOCIAL_MEDIA_SPECIALIST,
        VOLUNTEER,
        CONTRACTOR,
    }
)

# Scoped roles: one per project / one per task (Q-039).
SCOPE_TYPE_PROJECT = "project"
SCOPE_TYPE_TASK = "task"
SCOPED_ROLE_SCOPE_TYPE: dict[str, str] = {
    PROJECT_LEADER: SCOPE_TYPE_PROJECT,
    TASK_LEADER: SCOPE_TYPE_TASK,
}
SCOPED_ROLES: frozenset[str] = frozenset(SCOPED_ROLE_SCOPE_TYPE)

ALL_ROLES: frozenset[str] = GLOBAL_ROLES | SCOPED_ROLES

# Roles that must use two-step sign-in once enrolled (PRD §60.1); permissions activate only
# after enrollment (Q-045). Mirrors ham.rules.RULES.auth.MFA_REQUIRED_ROLES — kept here too so
# ``ham.authz`` (which must not import ``ham.rules``'s consumers) has a stable, importable
# constant; the rules module remains the source of truth and a test pins the two in sync.
MFA_REQUIRED_ROLES: frozenset[str] = frozenset(
    {ADMINISTRATOR, HAM_DIRECTOR, ASSISTANT_DIRECTOR, PASTOR, BOARD_REPRESENTATIVE}
)

ROLE_LABELS: dict[str, str] = {
    ADMINISTRATOR: "Administrator",
    HAM_DIRECTOR: "HAM Director",
    ASSISTANT_DIRECTOR: "Assistant Director",
    PASTOR: "Pastor",
    BOARD_REPRESENTATIVE: "Board representative",
    SOCIAL_MEDIA_SPECIALIST: "Social Media Specialist",
    VOLUNTEER: "Volunteer",
    CONTRACTOR: "Contractor",
    PROJECT_LEADER: "Project Leader",
    TASK_LEADER: "Task Leader",
}
