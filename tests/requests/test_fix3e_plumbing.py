"""Fix 3E item 5 (plumbing) and PRD re-check M4: the re-defer floor on a misfired early
held-effects retry, the dead `_route_from_post` removal, and a direct unit test for
`awaiting_site_visit_card`.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.db import connection

from ham.authz import roles
from ham.platform.clock import FixedClock, set_clock
from ham.requests.attention import awaiting_site_visit_card
from ham.requests.services_decisions import approve_request, run_held_decision_effects

from .conftest import actor_ctx
from .test_s32_decisions import _awaiting

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------------------
# Security L-a: the re-defer floor is `max(effective_at, now + 1s)`.
# ---------------------------------------------------------------------------------------
class TestRedeferFloor:
    def _scheduled_at(self, approval_id):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT scheduled_at FROM procrastinate_jobs WHERE task_name = %s "
                "AND args->>'approval_id' = %s ORDER BY id DESC LIMIT 1",
                ["requests.run_held_decision_effects", str(approval_id)],
            )
            row = cursor.fetchone()
        assert row is not None
        return row[0]

    def test_misfired_retry_just_before_effective_at_is_floored_at_now_plus_1s(
        self, requester_ctx, system_ctx, pastor_ctx
    ):
        req = _awaiting(requester_ctx, system_ctx)
        approval = approve_request(pastor_ctx, request_id=req.id, route="pastoral")
        # A retry landing 200ms before the window closes: `effective_at` itself is less than
        # 1 second away, so the floor (not `effective_at`) must win.
        near_miss = approval.effective_at - dt.timedelta(milliseconds=200)
        set_clock(FixedClock(near_miss))
        run_held_decision_effects(approval.id)
        scheduled_at = self._scheduled_at(approval.id)
        assert scheduled_at >= near_miss + dt.timedelta(seconds=1)
        assert scheduled_at != approval.effective_at
        set_clock(None)

    def test_retry_well_before_effective_at_still_uses_effective_at(
        self, requester_ctx, system_ctx, pastor_ctx
    ):
        req = _awaiting(requester_ctx, system_ctx)
        approval = approve_request(pastor_ctx, request_id=req.id, route="pastoral")
        far_before = approval.effective_at - dt.timedelta(minutes=10)
        set_clock(FixedClock(far_before))
        run_held_decision_effects(approval.id)
        scheduled_at = self._scheduled_at(approval.id)
        assert scheduled_at == approval.effective_at
        set_clock(None)


# ---------------------------------------------------------------------------------------
# Plumbing: the dead `_route_from_post` helper is gone.
# ---------------------------------------------------------------------------------------
class TestDeadRouteFromPostRemoved:
    def test_not_defined_anymore(self):
        from ham.web import views_requests

        assert not hasattr(views_requests, "_route_from_post")


# ---------------------------------------------------------------------------------------
# PRD re-check M4: a direct unit test for `awaiting_site_visit_card`.
# ---------------------------------------------------------------------------------------
class TestAwaitingSiteVisitCard:
    def test_none_for_a_role_without_dir_ad(self, requester_ctx, system_ctx, pastor_ctx):
        req = _awaiting(requester_ctx, system_ctx)
        approval = approve_request(pastor_ctx, request_id=req.id, route="pastoral")
        set_clock(FixedClock(approval.effective_at))
        assert awaiting_site_visit_card(pastor_ctx) is None
        set_clock(None)

    def test_none_while_the_decision_is_still_undoable(
        self, requester_ctx, system_ctx, pastor_ctx, director_ctx
    ):
        req = _awaiting(requester_ctx, system_ctx)
        approve_request(pastor_ctx, request_id=req.id, route="pastoral")
        assert awaiting_site_visit_card(director_ctx) is None

    def test_shown_once_settled_for_director(
        self, requester_ctx, system_ctx, pastor_ctx, director_ctx
    ):
        req = _awaiting(requester_ctx, system_ctx)
        approval = approve_request(pastor_ctx, request_id=req.id, route="pastoral")
        set_clock(FixedClock(approval.effective_at))
        card = awaiting_site_visit_card(director_ctx)
        assert card is not None
        assert card.count == 1
        assert card.actionable is False  # muted awareness card, not an action
        assert str(req.id) in card.href
        set_clock(None)

    def test_excluded_while_urgency_still_awaits_certification(
        self, requester_ctx, system_ctx, director_ctx
    ):
        board_ctx = actor_ctx(roles=frozenset({roles.BOARD_REPRESENTATIVE}))
        req = _awaiting(
            requester_ctx,
            system_ctx,
            urgent_requested=True,
            urgency_reason="someone_could_get_hurt",
        )
        approval = approve_request(board_ctx, request_id=req.id, route="board")
        set_clock(FixedClock(approval.effective_at))
        assert awaiting_site_visit_card(director_ctx) is None
        set_clock(None)

    def test_count_of_one_deep_links_straight_to_the_request(
        self, requester_ctx, system_ctx, pastor_ctx, director_ctx
    ):
        req = _awaiting(requester_ctx, system_ctx)
        approval = approve_request(pastor_ctx, request_id=req.id, route="pastoral")
        set_clock(FixedClock(approval.effective_at))
        card = awaiting_site_visit_card(director_ctx)
        assert card is not None
        assert card.href == f"/requests/{req.id}"
        set_clock(None)
