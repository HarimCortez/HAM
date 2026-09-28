"""Replays `tests/authz/expected_matrix.csv` (the independent permission oracle,
`generate_expected_matrix.py`) against `ham.authz.matrix.authorize`.

foundation.md §9.1: "a generator parametrizes: every action x every role x unauthenticated x
disabled x zero-role x representative role pairs x in/out of scope x impersonating". Any
mismatch between this CSV and the real matrix is either a bug in `ham/authz/matrix.py` or a
misreading of the PRD in the oracle — read `docs/HAM_PRD_V1.md` §67/§4.11 and
`docs/prd-open-questions.md` before "fixing" either side.
"""

from __future__ import annotations

import csv
import uuid
from pathlib import Path

import pytest

from ham.authz.context import ActorContext
from ham.authz.matrix import MATRIX, authorize

CSV_PATH = Path(__file__).resolve().parent / "expected_matrix.csv"


def _str_to_bool(value: str) -> bool:
    return value.strip().lower() in ("true", "1", "yes")


def _load_rows() -> list[dict[str, str]]:
    with CSV_PATH.open(newline="") as f:
        return list(csv.DictReader(f))


ROWS = _load_rows()


class _Resource:
    def __init__(self, user_id: object) -> None:
        self.user_id = user_id


def _ctx_for(row: dict[str, str]) -> tuple[ActorContext, object | None]:
    case = row["case"]
    self_user_id = uuid.uuid4()

    if case == "unauthenticated":
        return ActorContext.anonymous(), None

    if case == "zero_role":
        ctx = ActorContext(
            user_id=self_user_id,
            real_user_id=None,
            roles=frozenset(),
            is_active=True,
            mfa_satisfied=True,
        )
        return ctx, None

    if case == "disabled_user":
        ctx = ActorContext(
            user_id=self_user_id,
            real_user_id=None,
            roles=frozenset({row["role"]}),
            is_active=False,
            mfa_satisfied=True,
        )
        return ctx, None

    role_field = row["role"]
    role_set = frozenset(role_field.split("+")) if role_field else frozenset()

    mfa_satisfied = case not in (
        "mfa_role_unverified_alone",
        "mfa_role_unverified_union_with_volunteer",
    )

    impersonation_id = None
    if row["scope_case"] == "impersonating":
        impersonation_id = uuid.uuid4()

    ctx = ActorContext(
        user_id=self_user_id,
        real_user_id=None,
        roles=role_set,
        is_active=True,
        mfa_satisfied=mfa_satisfied,
        impersonation_id=impersonation_id,
    )

    resource = None
    if row["scope_case"] == "own":
        resource = _Resource(self_user_id)
    elif row["scope_case"] == "other":
        resource = _Resource(uuid.uuid4())

    return ctx, resource


@pytest.mark.parametrize("row", ROWS, ids=lambda r: f"{r['action']}[{r['case']}:{r['role']}]")
def test_expected_matrix_row(row):
    ctx, resource = _ctx_for(row)
    decision = authorize(ctx, row["action"], resource)

    expected_allowed = _str_to_bool(row["expected_allowed"])
    assert decision.allowed is expected_allowed, (
        f"{row['action']} / role={row['role']!r} / case={row['case']} / "
        f"scope={row['scope_case']}: expected allowed={expected_allowed}, "
        f"got {decision.allowed} ({decision.reason})"
    )

    # step-up/impersonation flags are only asserted on baseline/role_union rows (the ones the
    # oracle actually populated with a real step-up expectation); the mfa/zero-role/scope rows
    # focus on the allow/deny outcome, which is what those cases probe.
    if row["case"] in ("baseline", "role_union") and expected_allowed:
        expected_step_up = _str_to_bool(row["expected_step_up_required"])
        assert decision.step_up_required is expected_step_up, (
            f"{row['action']} / role={row['role']!r}: expected step_up_required="
            f"{expected_step_up}, got {decision.step_up_required}"
        )


def test_every_matrix_action_is_covered_by_the_oracle():
    """The oracle must not silently drift behind new actions added to the matrix."""
    oracle_actions = {row["action"] for row in ROWS}
    assert oracle_actions == set(MATRIX), (
        f"MATRIX has actions the oracle doesn't cover: {set(MATRIX) - oracle_actions}, or the "
        f"oracle covers actions no longer in MATRIX: {oracle_actions - set(MATRIX)}"
    )


def test_unknown_action_denied_independent_of_role():
    ctx = ActorContext(
        user_id=uuid.uuid4(),
        real_user_id=None,
        roles=frozenset({"ADMINISTRATOR"}),
        is_active=True,
        mfa_satisfied=True,
    )
    decision = authorize(ctx, "not.a.real.action")
    assert decision.allowed is False
