"""FIX-3A view-level logic: PRD guardian B1 (Board approves an urgent request), M1/security
L6/Q-164 (no preselected route, 422 on a missing one), PRD guardian B2 (Board-route
reconsideration threads `board_decided_on`), security M4 (no GET reveal), security L3
(malformed id -> 404, never a 500), security L4 (server-side text limits), Q-183 (a
role_ended take-over carries no tick).
"""

from __future__ import annotations

import uuid

import pytest
from django.urls import reverse

from ham.audit.models import AuditEvent
from ham.identity.models import RoleAssignment, SharedIdentityProfile
from ham.platform.clock import FixedClock, set_clock
from ham.platform.clock import now as clock_now
from ham.requests.models import Approval
from ham.requests.presentation import DECLINE_MESSAGE_MAX_CHARS
from ham.requests.services_decisions import reject_request, request_reconsideration
from ham.requests.states import RequestStatus, UrgencyStatus
from tests.requests.conftest import actor_ctx
from tests.web.test_s36_leadership_screens import _ctx_for, _login, _make_request

pytestmark = pytest.mark.django_db


@pytest.fixture
def requester_ctx():
    from ham.authz.context import RequesterContext

    return RequesterContext(request_id=None)


@pytest.fixture
def system_ctx():
    from ham.authz.context import SystemContext

    return SystemContext()


class TestB1BoardApprovesUrgentRequest:
    def test_board_rep_approves_an_urgent_flagged_request(self, client, make_user):
        req = _make_request(urgent_requested=True, urgency_reason="someone_could_get_hurt")
        _login(
            client,
            make_user,
            email="marcus@example.org",
            full_name="Marcus B",
            role="BOARD_REPRESENTATIVE",
        )

        # The real sheet's hidden field carries this for a single-role viewer; posted
        # explicitly here since the test bypasses the template. `mode=not_urgent` reproduces
        # the exact pre-fix template bug (B1): the old hidden `mode` field defaulted to
        # "not_urgent" for EVERY urgent-awaiting-cert viewer, board reps included.
        response = client.post(
            reverse("web:request_approve", args=[req.id]),
            {"route": "board", "mode": "not_urgent"},
        )

        assert response.status_code == 302
        req.refresh_from_db()
        assert req.status == RequestStatus.APPROVED.value
        # The Board route never touches urgency review -- it stays exactly where it was.
        assert req.urgency_status == UrgencyStatus.AWAITING_CERTIFICATION.value

    def test_dual_role_user_choosing_board_leaves_urgency_awaiting(self, client, make_user):
        req = _make_request(urgent_requested=True, urgency_reason="someone_could_get_hurt")
        user = make_user("dual@example.org")
        SharedIdentityProfile.objects.create(user=user, full_name="Dual Role")
        RoleAssignment.objects.create(user=user, role="PASTOR", granted_at=clock_now())
        RoleAssignment.objects.create(
            user=user, role="BOARD_REPRESENTATIVE", granted_at=clock_now()
        )
        client.force_login(user)
        session = client.session
        session["ham_mfa_satisfied"] = True
        session.save()

        response = client.post(reverse("web:request_approve", args=[req.id]), {"route": "board"})
        assert response.status_code == 302
        req.refresh_from_db()
        assert req.status == RequestStatus.APPROVED.value
        assert req.urgency_status == UrgencyStatus.AWAITING_CERTIFICATION.value


class TestM1NoPreselectedRoute:
    """PRD guardian M1 / security L6 / Q-164: nothing is preselected for a dual-role user --
    the server refuses (422), it never silently defaults, on a missing route."""

    def test_dual_role_missing_route_is_refused_with_422(self, client, make_user):
        req = _make_request()
        user = make_user("dual2@example.org")
        SharedIdentityProfile.objects.create(user=user, full_name="Dual Two")
        RoleAssignment.objects.create(user=user, role="PASTOR", granted_at=clock_now())
        RoleAssignment.objects.create(
            user=user, role="BOARD_REPRESENTATIVE", granted_at=clock_now()
        )
        client.force_login(user)
        session = client.session
        session["ham_mfa_satisfied"] = True
        session.save()

        response = client.post(reverse("web:request_approve", args=[req.id]))
        assert response.status_code == 422
        req.refresh_from_db()
        assert req.status == RequestStatus.AWAITING_APPROVAL.value
        assert not Approval.objects.filter(request_id=req.id).exists()

    def test_dual_role_missing_route_on_decline_is_refused_with_422(self, client, make_user):
        req = _make_request()
        user = make_user("dual3@example.org")
        SharedIdentityProfile.objects.create(user=user, full_name="Dual Three")
        RoleAssignment.objects.create(user=user, role="PASTOR", granted_at=clock_now())
        RoleAssignment.objects.create(
            user=user, role="BOARD_REPRESENTATIVE", granted_at=clock_now()
        )
        client.force_login(user)
        session = client.session
        session["ham_mfa_satisfied"] = True
        session.save()

        response = client.post(
            reverse("web:request_reject", args=[req.id]),
            {"reason_code": "another_reason", "message": "Sorry, we can't help."},
        )
        assert response.status_code == 422
        req.refresh_from_db()
        assert req.status == RequestStatus.AWAITING_APPROVAL.value


class TestB2BoardRouteReconsideration:
    """PRD guardian B2 / Q-180: the Board-route reconsideration decision needs
    `board_decided_on`, which previously was never threaded through at all -- an
    `IntegrityError`, not a clean refusal."""

    def test_board_route_reconsideration_records_board_decided_on(self, client, make_user):
        req = _make_request()
        board_user = _login(
            client,
            make_user,
            email="marcus@example.org",
            full_name="Marcus B",
            role="BOARD_REPRESENTATIVE",
        )
        approval = reject_request(
            _ctx_for(board_user, "BOARD_REPRESENTATIVE"),
            request_id=req.id,
            route="board",
            reason_code="another_reason",
            message="Sorry",
        )
        req.refresh_from_db()
        set_clock(FixedClock(approval.effective_at))
        from ham.authz.context import RequesterContext

        request_reconsideration(RequesterContext(request_id=req.id))
        req.refresh_from_db()

        response = client.post(
            reverse("web:request_reconsideration_decide", args=[req.id]),
            {"outcome": "approve", "reason": "Second look", "board_decided_on": ""},
        )
        assert response.status_code == 302
        req.refresh_from_db()
        assert req.status == RequestStatus.APPROVED.value
        recon_approval = Approval.objects.get(request_id=req.id, stage="reconsideration")
        assert recon_approval.board_decided_on is not None


class TestQ183RoleEndedTakeover:
    def test_role_ended_takeover_has_no_tick_and_audit_carries_the_basis(
        self, requester_ctx, system_ctx, make_user
    ):
        from ham.authz import roles
        from ham.identity.models import RoleAssignment as RA
        from ham.requests.services_decisions import decide_reconsideration
        from tests.requests.test_s32_decisions import _awaiting

        # Build an original decider who is later removed from the Pastor role.
        original_user = make_user("orig@example.org")
        RA.objects.create(user=original_user, role=roles.PASTOR, granted_at=clock_now())
        original_ctx = actor_ctx(roles=frozenset({roles.PASTOR}), user_id=original_user.id)

        req = _awaiting(requester_ctx, system_ctx)
        approval = reject_request(
            original_ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="another_reason",
            message="Sorry",
        )
        req.refresh_from_db()
        set_clock(FixedClock(approval.effective_at))
        from ham.authz.context import RequesterContext

        request_reconsideration(RequesterContext(request_id=req.id))

        # The original pastor's role ends.
        RA.objects.filter(user=original_user, role=roles.PASTOR).update(revoked_at=clock_now())

        other_user = make_user("other@example.org")
        RA.objects.create(user=other_user, role=roles.PASTOR, granted_at=clock_now())
        other_ctx = actor_ctx(roles=frozenset({roles.PASTOR}), user_id=other_user.id)

        recon_approval = decide_reconsideration(
            other_ctx, request_id=req.id, approve=True, reason="Second look"
        )
        assert recon_approval.took_over_basis == "role_ended"
        assert recon_approval.unavailable_confirmed is False

        audit = AuditEvent.objects.filter(
            action="request.reconsideration_decided", target_id=str(req.id)
        ).latest("occurred_at")
        assert audit.after["took_over"] is True
        assert audit.after["take_over_basis"] == "role_ended"


class TestSecurityM4NoRevealOnGet:
    def test_get_on_ask_question_never_reveals_for_a_no_email_request(self, client, make_user):
        from tests.web.test_s36_leadership_screens import _make_no_email_request

        req = _make_no_email_request()
        _login(client, make_user, email="ruth@example.org", full_name="Ruth A", role="PASTOR")
        before = AuditEvent.objects.filter(action="requester_pii.revealed").count()

        response = client.get(reverse("web:request_question_ask", args=[req.id]))
        assert response.status_code == 200
        after = AuditEvent.objects.filter(action="requester_pii.revealed").count()
        assert after == before, "a GET must never write a requester_pii.revealed audit row"
        assert "Show contact details" in response.content.decode()

    def test_post_show_contact_reveals_exactly_once(self, client, make_user):
        from tests.web.test_s36_leadership_screens import _make_no_email_request

        req = _make_no_email_request()
        _login(client, make_user, email="ruth@example.org", full_name="Ruth A", role="PASTOR")
        before = AuditEvent.objects.filter(action="requester_pii.revealed").count()

        response = client.post(
            reverse("web:request_question_ask", args=[req.id]), {"show_contact": "1"}
        )
        assert response.status_code == 200
        after = AuditEvent.objects.filter(action="requester_pii.revealed").count()
        assert after == before + 1


class TestSecurityL3MalformedId:
    def test_undo_with_malformed_approval_id_is_404_not_500(self, client, make_user):
        req = _make_request()
        _login(client, make_user, email="ruth@example.org", full_name="Ruth A", role="PASTOR")
        response = client.get(
            reverse("web:request_decision_undo", args=[req.id]) + "?approval_id=not-a-uuid"
        )
        assert response.status_code == 404


class TestSecurityL4TextLimits:
    def test_decline_message_over_the_limit_is_refused_server_side(self, client, make_user):
        req = _make_request()
        _login(client, make_user, email="ruth@example.org", full_name="Ruth A", role="PASTOR")
        too_long = "x" * (DECLINE_MESSAGE_MAX_CHARS + 1)
        response = client.post(
            reverse("web:request_reject", args=[req.id]),
            {"route": "pastoral", "reason_code": "another_reason", "message": too_long},
        )
        assert response.status_code == 422
        req.refresh_from_db()
        assert req.status == RequestStatus.AWAITING_APPROVAL.value
        assert not Approval.objects.filter(request_id=req.id).exists()


class TestVisualM4DecidedTabExcludesCancelled:
    def test_cancelled_request_does_not_appear_in_the_decided_tab(self, requester_ctx, system_ctx):
        from ham.requests.queries import list_requests
        from ham.requests.services import cancel_request
        from tests.requests.test_s32_decisions import _awaiting

        req = _awaiting(requester_ctx, system_ctx)
        director_ctx = actor_ctx(roles=frozenset({"HAM_DIRECTOR"}))
        cancel_request(director_ctx, request_id=req.id, reason_code="spam", note="")
        rows = list_requests(director_ctx, view="decided")
        assert req.id not in {r.id for r in rows}


class TestVisualM5WaitingOnRequesterQuery:
    def test_a_request_with_no_questions_at_all_is_never_listed(self, requester_ctx, system_ctx):
        from ham.requests.queries_questions import waiting_on_requester
        from tests.requests.test_s32_decisions import _awaiting

        req = _awaiting(requester_ctx, system_ctx)
        director_ctx = actor_ctx(roles=frozenset({"HAM_DIRECTOR"}))
        rows = waiting_on_requester(director_ctx)
        assert req.id not in {r.id for r in rows}

    def test_a_request_with_an_open_question_is_listed(self, requester_ctx, system_ctx):
        from ham.requests.models import RequestQuestion
        from ham.requests.queries_questions import waiting_on_requester
        from tests.requests.test_s32_decisions import _awaiting

        req = _awaiting(requester_ctx, system_ctx)
        director_ctx = actor_ctx(roles=frozenset({"HAM_DIRECTOR"}))
        RequestQuestion.objects.create(
            request=req, asked_by_user_id=uuid.uuid4(), asked_at=clock_now(), question="?"
        )
        rows = waiting_on_requester(director_ctx)
        assert req.id in {r.id for r in rows}
