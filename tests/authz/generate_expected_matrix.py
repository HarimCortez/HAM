"""Generates ``tests/authz/expected_matrix.csv``, the test engineer's independent permission
oracle (foundation.md §9.1).

This is deliberately NOT built from ``ham/authz/matrix.py``. Every allowed-roles set below was
typed by re-reading PRD §67 ("Permission Principles"), §4.11 (per-role responsibilities) and
§68 (privacy), plus the decided rows of ``docs/prd-open-questions.md``: Q-041 (Director's
grantable roles), Q-045 (MFA role activates only after enrollment), Q-054 (leader assignment
excludes Administrator), Q-055 (Director role-grant guardrails — enforced in the service layer,
not the matrix scope, so not visible here), Q-021 (no per-project activity history for Project
Leaders), Q-034/Q-046/Q-048 (impersonation step-up and blocked-action list), Q-080/Q-081
(placeholders for not-yet-built actions). Role name strings are typed literally (not imported
from ``ham.authz.roles``) so a typo in that module can't silently match this file too.

Run to regenerate after a deliberate, reviewed change to the oracle (never to "make the test
pass" — a mismatch against ``ham.authz.authorize`` means either this file or the application
code is wrong; read the PRD before touching either):

    PYTHONPATH=. python tests/authz/generate_expected_matrix.py
"""

from __future__ import annotations

import csv
from pathlib import Path

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

ALL_ROLES = (
    ADMINISTRATOR,
    HAM_DIRECTOR,
    ASSISTANT_DIRECTOR,
    PASTOR,
    BOARD_REPRESENTATIVE,
    SOCIAL_MEDIA_SPECIALIST,
    VOLUNTEER,
    CONTRACTOR,
    PROJECT_LEADER,
    TASK_LEADER,
)

# MFA-required roles (PRD §60.1): permissions activate only once enrolled (Q-045).
MFA_ROLES = frozenset(
    {ADMINISTRATOR, HAM_DIRECTOR, ASSISTANT_DIRECTOR, PASTOR, BOARD_REPRESENTATIVE}
)

ANY = "any"
SELF = "self"

# action -> (allowed_roles, scope, step_up_required, blocked_while_impersonating, prd_refs)
ORACLE: dict[str, tuple[frozenset[str], str, bool, bool, str]] = {
    # Every standing role reaches the shell and their own profile (§67 per-role summaries all
    # presuppose the person can sign in and see their own information).
    "shell.use": (frozenset(ALL_ROLES), ANY, False, False, "§67"),
    "me.view": (frozenset(ALL_ROLES), SELF, False, False, "§67"),
    "me.update": (frozenset(ALL_ROLES), SELF, False, False, "§67"),
    # Q-048 expanded blocked-action list: "MFA/security changes" blocked while impersonating.
    "me.security.manage": (frozenset(ALL_ROLES), SELF, False, True, "§60, Q-048"),
    "me.recovery_codes.regenerate": (frozenset(ALL_ROLES), SELF, True, True, "§60.1, Q-046"),
    "me.sign_in_email.change": (frozenset(ALL_ROLES), SELF, True, True, "§60.2, Q-051, Q-046"),
    # §4.11 "configuration"; Q-007 (church contact info is Admin-editable).
    "church_profile.update": (frozenset({ADMINISTRATOR}), ANY, False, True, "§4.11, Q-007"),
    # Q-041: "Director gets user.list/user.view."
    "user.list": (frozenset({ADMINISTRATOR, HAM_DIRECTOR}), ANY, False, False, "§4.11, Q-041"),
    "user.view": (frozenset({ADMINISTRATOR, HAM_DIRECTOR}), ANY, False, False, "§4.11, Q-041"),
    # Q-037: Admin, Director, Assistant Director may invite (AD limited to Volunteer at the
    # service layer per Q-082 — not a matrix-level distinction). Q-080: blocked while
    # impersonating (an admin action on someone else's account).
    "user.invite": (
        frozenset({ADMINISTRATOR, HAM_DIRECTOR, ASSISTANT_DIRECTOR}),
        ANY,
        False,
        True,
        "§4.11, Q-037, Q-080",
    ),
    # §4.11 lists "users" under Administrator only; Q-079 leaves Director's disable/enable
    # open, so this stays Administrator-only until decided.
    "user.update_identity": (frozenset({ADMINISTRATOR}), ANY, False, False, "§4.11"),
    "user.disable": (frozenset({ADMINISTRATOR}), ANY, False, True, "§4.11, Q-035, Q-079, Q-080"),
    "user.enable": (frozenset({ADMINISTRATOR}), ANY, False, True, "§4.11, Q-080"),
    # Q-035/Q-044: only an Administrator resets another person's MFA, never their own.
    "user.mfa_reset": (frozenset({ADMINISTRATOR}), ANY, True, True, "§60.1, Q-035, Q-044"),
    # Q-041: Director may grant/remove every role except Administrator (the "except
    # Administrator" carve-out is enforced by the service, not the matrix scope rule — see
    # ham/identity/services.py; this oracle only asserts the matrix-level role check).
    "role.grant_global": (
        frozenset({ADMINISTRATOR, HAM_DIRECTOR}),
        ANY,
        True,
        True,
        "§4.11, §58, Q-041, Q-046",
    ),
    "role.revoke_global": (
        frozenset({ADMINISTRATOR, HAM_DIRECTOR}),
        ANY,
        True,
        True,
        "§4.11, §58, Q-041, Q-046",
    ),
    # Q-054: NOT the Administrator, per PRD §16/§17 ("Director/Assistant Director").
    "leader.project.assign": (
        frozenset({HAM_DIRECTOR, ASSISTANT_DIRECTOR}),
        ANY,
        False,
        True,
        "§16, Q-031, Q-054",
    ),
    "leader.project.revoke": (
        frozenset({HAM_DIRECTOR, ASSISTANT_DIRECTOR}),
        ANY,
        False,
        True,
        "§16, Q-031, Q-054",
    ),
    "leader.task.assign": (
        frozenset({HAM_DIRECTOR, ASSISTANT_DIRECTOR}),
        ANY,
        False,
        True,
        "§17, Q-031, Q-054",
    ),
    "leader.task.revoke": (
        frozenset({HAM_DIRECTOR, ASSISTANT_DIRECTOR}),
        ANY,
        False,
        True,
        "§17, Q-031, Q-054",
    ),
    # Q-021: no per-project activity history for Project Leaders -> audit stays Admin/Director.
    "audit.view": (frozenset({ADMINISTRATOR, HAM_DIRECTOR}), ANY, False, False, "§58, §67, Q-021"),
    "audit.export": (
        frozenset({ADMINISTRATOR, HAM_DIRECTOR}),
        ANY,
        True,
        True,
        "§58, Q-010, Q-046",
    ),
    # PRD §67 HAM Director bullet list explicitly names "deleted-comment audit access".
    "audit.view_deleted_comment": (
        frozenset({ADMINISTRATOR, HAM_DIRECTOR}),
        ANY,
        False,
        True,
        "§57, §67",
    ),
    # Q-034: Administrator only.
    "impersonation.start": (frozenset({ADMINISTRATOR}), ANY, True, True, "§59, Q-034, Q-046"),
    # Special-cased: no role grants this; only "currently impersonating" (any actor) may stop.
    # Handled separately in the test, not a normal allowed-roles row.
    "impersonation.stop": (frozenset(), "impersonating_only", False, False, "§59"),
    # §4.11 "integrations", "troubleshooting".
    "integrations.view_status": (frozenset({ADMINISTRATOR}), ANY, False, False, "§4.11"),
    "rules.view": (frozenset({ADMINISTRATOR, HAM_DIRECTOR}), ANY, False, False, "§4.11"),
    "outbox.retry": (frozenset({ADMINISTRATOR}), ANY, False, True, "§70.3, §4.11"),
    # Q-081: placeholder until the requests/projects data model exists -> always denies.
    "requester_pii.reveal": (frozenset(), ANY, False, False, "§67, §68, Q-009, Q-024, Q-081"),
}

OUT_PATH = Path(__file__).resolve().parent / "expected_matrix.csv"

FIELDNAMES = [
    "action",
    "role",
    "scope_case",
    "expected_allowed",
    "expected_step_up_required",
    "expected_blocked_while_impersonating",
    "prd_ref",
    "case",
]


def _rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []

    for action, (allowed_roles, scope, step_up, blocked_ib, prd_ref) in ORACLE.items():
        if scope == "impersonating_only":
            # impersonation.stop: allowed for the currently-impersonating actor regardless of
            # role; denied for everyone else, regardless of role (even Administrator).
            rows.append(
                dict(
                    action=action,
                    role=ADMINISTRATOR,
                    scope_case="impersonating",
                    expected_allowed=True,
                    expected_step_up_required=False,
                    expected_blocked_while_impersonating=False,
                    prd_ref=prd_ref,
                    case="baseline",
                )
            )
            rows.append(
                dict(
                    action=action,
                    role=VOLUNTEER,
                    scope_case="impersonating",
                    expected_allowed=True,
                    expected_step_up_required=False,
                    expected_blocked_while_impersonating=False,
                    prd_ref=prd_ref,
                    case="baseline",
                )
            )
            rows.append(
                dict(
                    action=action,
                    role=ADMINISTRATOR,
                    scope_case="not_impersonating",
                    expected_allowed=False,
                    expected_step_up_required=False,
                    expected_blocked_while_impersonating=False,
                    prd_ref=prd_ref,
                    case="baseline",
                )
            )
            continue

        scope_cases = [SELF] if scope == SELF else [ANY]
        for role in ALL_ROLES:
            allowed = role in allowed_roles
            for scope_case in scope_cases:
                # SELF-scope actions: also test "someone else's record" (always denied,
                # regardless of role, since the matrix scope check runs after the role check).
                own_or_any_allowed = allowed
                rows.append(
                    dict(
                        action=action,
                        role=role,
                        scope_case="own" if scope_case == SELF else "n/a",
                        expected_allowed=own_or_any_allowed,
                        expected_step_up_required=step_up if allowed else False,
                        expected_blocked_while_impersonating=blocked_ib if allowed else False,
                        prd_ref=prd_ref,
                        case="baseline",
                    )
                )
                if scope_case == SELF:
                    rows.append(
                        dict(
                            action=action,
                            role=role,
                            scope_case="other",
                            expected_allowed=False,
                            expected_step_up_required=False,
                            expected_blocked_while_impersonating=False,
                            prd_ref=prd_ref,
                            case="scope_out_of_bounds",
                        )
                    )

        # Zero-role / unauthenticated / disabled: always denied, no matter the action.
        rows.append(
            dict(
                action=action,
                role="",
                scope_case="n/a",
                expected_allowed=False,
                expected_step_up_required=False,
                expected_blocked_while_impersonating=False,
                prd_ref=prd_ref,
                case="zero_role",
            )
        )
        rows.append(
            dict(
                action=action,
                role="",
                scope_case="n/a",
                expected_allowed=False,
                expected_step_up_required=False,
                expected_blocked_while_impersonating=False,
                prd_ref=prd_ref,
                case="unauthenticated",
            )
        )
        rows.append(
            dict(
                action=action,
                role=ADMINISTRATOR,
                scope_case="n/a",
                expected_allowed=False,
                expected_step_up_required=False,
                expected_blocked_while_impersonating=False,
                prd_ref=prd_ref,
                case="disabled_user",
            )
        )

        # MFA-role union: an MFA-required role held with no other standing role, and MFA not
        # yet satisfied (Q-045), never grants anything (effective_roles strips it entirely) —
        # also test the SAME role combined with VOLUNTEER, which keeps VOLUNTEER's grants only.
        for mfa_role in (HAM_DIRECTOR,):
            if mfa_role in MFA_ROLES:
                rows.append(
                    dict(
                        action=action,
                        role=mfa_role,
                        scope_case="n/a",
                        expected_allowed=False,
                        expected_step_up_required=False,
                        expected_blocked_while_impersonating=False,
                        prd_ref=prd_ref,
                        case="mfa_role_unverified_alone",
                    )
                )
                rows.append(
                    dict(
                        action=action,
                        role=f"{mfa_role}+{VOLUNTEER}",
                        scope_case="n/a",
                        expected_allowed=VOLUNTEER in allowed_roles,
                        expected_step_up_required=False,
                        expected_blocked_while_impersonating=False,
                        prd_ref=prd_ref,
                        case="mfa_role_unverified_union_with_volunteer",
                    )
                )

        # Role union: Volunteer + Administrator should get the union (higher privilege wins,
        # §4.11 "when role permissions conflict, the higher-privilege permission applies").
        union_role = f"{VOLUNTEER}+{ADMINISTRATOR}"
        rows.append(
            dict(
                action=action,
                role=union_role,
                scope_case="own" if scope == SELF else "n/a",
                expected_allowed=(ADMINISTRATOR in allowed_roles) or (VOLUNTEER in allowed_roles),
                expected_step_up_required=step_up
                if (ADMINISTRATOR in allowed_roles or VOLUNTEER in allowed_roles)
                else False,
                expected_blocked_while_impersonating=blocked_ib
                if (ADMINISTRATOR in allowed_roles or VOLUNTEER in allowed_roles)
                else False,
                prd_ref=prd_ref,
                case="role_union",
            )
        )

    return rows


def main() -> None:
    rows = _rows()
    with OUT_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    print(f"Wrote {len(rows)} rows to {OUT_PATH}")


if __name__ == "__main__":
    main()
