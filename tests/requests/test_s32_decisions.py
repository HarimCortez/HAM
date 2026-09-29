"""S3.2: the real decisions-core commands (approvals.md §2.2-§2.4; approvals-contracts.md §2,
§4) -- approve/reject/certify/decline, reconsideration (request/phone/decide), finalize + its
hourly job, decision-phoned, category change, undo, and the held-effects job.
"""

from __future__ import annotations

import threading
import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from ham.audit.models import AuditEvent
from ham.authz import roles
from ham.authz.commands import ImpersonationBlocked, PermissionDenied
from ham.outbox.models import OutboxEvent
from ham.platform.clock import FixedClock, set_clock
from ham.platform.clock import now as clock_now
from ham.requests.models import (
    Approval,
    ApprovalOutcome,
    ApprovalRoute,
    ApprovalStage,
    Reconsideration,
)
from ham.requests.services import cancel_request, complete_intake_checks, submit_request
from ham.requests.services_decisions import (
    approve_request,
    change_category,
    decide_reconsideration,
    finalize_rejection,
    record_decision_phoned,
    record_reconsideration_by_phone,
    reject_request,
    request_reconsideration,
    review_urgency,
    run_held_decision_effects,
    undo_decision,
)
from ham.requests.states import RequestStatus, UrgencyStatus
from ham.rules import RULES

from .conftest import actor_ctx, make_payload, no_email_payload

pytestmark = pytest.mark.django_db


def _awaiting(requester_ctx, system_ctx, **overrides):
    req = submit_request(
        requester_ctx,
        draft_id=uuid.uuid4(),
        verification_id=uuid.uuid4(),
        payload=make_payload(**overrides),
    )
    complete_intake_checks(system_ctx, request_id=req.id)
    req.refresh_from_db()
    return req


def _no_email_awaiting(requester_ctx, system_ctx, director_ctx):
    from ham.requests.services import verify_by_phone

    req = submit_request(
        requester_ctx,
        draft_id=uuid.uuid4(),
        verification_id=uuid.uuid4(),
        payload=no_email_payload(),
    )
    verify_by_phone(director_ctx, request_id=req.id)
    complete_intake_checks(system_ctx, request_id=req.id)
    req.refresh_from_db()
    return req


def _urgent_awaiting(requester_ctx, system_ctx, **overrides):
    # Q-160/M4: "someone_could_get_hurt" needs no free-text justification, unlike
    # "something_else" -- keeps these fixtures simple.
    overrides.setdefault("urgency_reason", "someone_could_get_hurt")
    return _awaiting(requester_ctx, system_ctx, urgent_requested=True, **overrides)


def _active_pastor_ctx(make_user):
    from ham.identity.models import RoleAssignment
    from ham.platform.clock import now as clock_now

    user = make_user(f"pastor-{uuid.uuid4()}@example.org")
    RoleAssignment.objects.create(user=user, role=roles.PASTOR, granted_at=clock_now())
    return actor_ctx(roles=frozenset({roles.PASTOR}), user_id=user.id)


def _impersonating(base_ctx):
    import dataclasses

    return dataclasses.replace(base_ctx, impersonation_id=uuid.uuid4(), real_user_id=uuid.uuid4())


# ------------------------------------------------------------------------------------------
# approve_request
# ------------------------------------------------------------------------------------------
class TestApproveRequest:
    def test_approve_records_audit_and_holds_the_outbox_event(
        self, requester_ctx, system_ctx, pastor_ctx
    ):
        req = _awaiting(requester_ctx, system_ctx)
        approval = approve_request(pastor_ctx, request_id=req.id, route="pastoral")

        req.refresh_from_db()
        assert req.status == RequestStatus.APPROVED.value
        assert approval.outcome == ApprovalOutcome.APPROVED.value
        assert approval.route == ApprovalRoute.PASTORAL.value
        assert approval.decided_by_user_id == pastor_ctx.user_id
        assert approval.effective_at == approval.decided_at + RULES.approvals.DECISION_UNDO_WINDOW

        events = list(AuditEvent.objects.filter(action="request.approved"))
        assert len(events) == 1
        assert events[0].after == {
            "route": "pastoral",
            "stage": "initial",
            "urgent_approval": False,
            "approval_id": str(approval.id),
        }
        # Held: no RequestApproved/RequestRejected outbox event yet, at decide time.
        assert not OutboxEvent.objects.filter(event_type="RequestApproved").exists()

    def test_board_route_prefills_todays_board_decided_on(
        self, requester_ctx, system_ctx, board_rep_ctx
    ):
        req = _awaiting(requester_ctx, system_ctx)
        approval = approve_request(board_rep_ctx, request_id=req.id, route="board")
        from zoneinfo import ZoneInfo

        from ham.platform.church import church_profile

        expected = timezone.now().astimezone(ZoneInfo(church_profile().time_zone)).date()
        assert approval.board_decided_on == expected

    def test_board_decided_on_in_the_future_is_refused(
        self, requester_ctx, system_ctx, board_rep_ctx
    ):
        req = _awaiting(requester_ctx, system_ctx)
        with pytest.raises(ValueError, match="future"):
            approve_request(
                board_rep_ctx,
                request_id=req.id,
                route="board",
                board_decided_on=timezone.now().date() + timedelta(days=1),
            )

    def test_wrong_role_is_denied(self, requester_ctx, system_ctx, director_ctx):
        req = _awaiting(requester_ctx, system_ctx)
        with pytest.raises(PermissionDenied):
            approve_request(director_ctx, request_id=req.id, route="pastoral")

    def test_blocked_while_impersonating(self, requester_ctx, system_ctx, pastor_ctx):
        req = _awaiting(requester_ctx, system_ctx)
        with pytest.raises(ImpersonationBlocked):
            approve_request(_impersonating(pastor_ctx), request_id=req.id, route="pastoral")

    def test_wrong_state_is_refused(self, requester_ctx, system_ctx, pastor_ctx):
        req = _awaiting(requester_ctx, system_ctx)
        approve_request(pastor_ctx, request_id=req.id, route="pastoral")
        with pytest.raises(ValueError, match="wrong_state"):
            approve_request(pastor_ctx, request_id=req.id, route="pastoral")

    def test_certify_urgent_writes_two_audit_events_and_emits_urgencycertified_immediately(
        self, requester_ctx, system_ctx, pastor_ctx
    ):
        req = _urgent_awaiting(requester_ctx, system_ctx)
        assert req.urgency_status == UrgencyStatus.AWAITING_CERTIFICATION.value
        approval = approve_request(
            pastor_ctx, request_id=req.id, route="pastoral", certify_urgent=True
        )
        assert approval.urgent_approval is True

        assert AuditEvent.objects.filter(action="request.approved").count() == 1
        assert AuditEvent.objects.filter(action="request.urgency_certified").count() == 1
        urgent_events = OutboxEvent.objects.filter(event_type="UrgencyCertified")
        assert urgent_events.count() == 1
        assert urgent_events.first().payload == {"request_id": str(req.id)}
        # The dedicated immediate alert fires once, distinct from the held RequestApproved.
        alert = OutboxEvent.objects.get(event_type="RequestUrgentApproval")
        assert alert.payload == {"request_id": str(req.id), "approval_id": str(approval.id)}
        assert not OutboxEvent.objects.filter(event_type="RequestApproved").exists()

    def test_decline_urgency_while_approving_emits_urgencynotcertified_immediately(
        self, requester_ctx, system_ctx, pastor_ctx
    ):
        req = _urgent_awaiting(requester_ctx, system_ctx)
        approval = approve_request(
            pastor_ctx, request_id=req.id, route="pastoral", decline_urgency=True
        )
        assert approval.urgent_approval is False
        req.refresh_from_db()
        assert req.urgency_status == UrgencyStatus.NOT_CERTIFIED.value
        assert OutboxEvent.objects.filter(event_type="UrgencyNotCertified").count() == 1
        assert not OutboxEvent.objects.filter(event_type="RequestApproved").exists()

    def test_approving_an_already_certified_request_emits_the_dedicated_alert_not_requestapproved(
        self, requester_ctx, system_ctx, pastor_ctx, board_rep_ctx
    ):
        req = _urgent_awaiting(requester_ctx, system_ctx)
        review_urgency(pastor_ctx, request_id=req.id, certify=True)
        approval = approve_request(board_rep_ctx, request_id=req.id, route="board")
        assert approval.urgent_approval is True
        assert not OutboxEvent.objects.filter(event_type="RequestApproved").exists()
        alert = OutboxEvent.objects.get(event_type="RequestUrgentApproval")
        assert alert.payload == {"request_id": str(req.id), "approval_id": str(approval.id)}

    def test_message_and_note_text_never_appear_in_audit_or_outbox(
        self, requester_ctx, system_ctx, pastor_ctx
    ):
        req = _awaiting(requester_ctx, system_ctx)
        approve_request(
            pastor_ctx,
            request_id=req.id,
            route="pastoral",
            approval_note="Secret leaders-only note",
        )
        for event in AuditEvent.objects.all():
            blob = str(event.before) + str(event.after) + str(event.context) + event.reason
            assert "Secret leaders-only note" not in blob
        for event in OutboxEvent.objects.all():
            assert "Secret leaders-only note" not in str(event.payload)


# ------------------------------------------------------------------------------------------
# reject_request
# ------------------------------------------------------------------------------------------
class TestRejectRequest:
    def test_reject_sets_deadline_and_holds_the_outbox_event(
        self, requester_ctx, system_ctx, pastor_ctx
    ):
        req = _awaiting(requester_ctx, system_ctx)
        approval = reject_request(
            pastor_ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="another_reason",
            message="It looks like this can be met another way.",
        )
        req.refresh_from_db()
        assert req.status == RequestStatus.REJECTED.value
        assert req.closed_at is None  # still open: can be reconsidered
        assert req.reconsideration_deadline_at is not None
        assert approval.reason_code == "another_reason"

        audit = AuditEvent.objects.get(action="request.rejected")
        assert audit.after == {
            "route": "pastoral",
            "stage": "initial",
            "reason_code": "another_reason",
            "urgent_approval": False,
            "approval_id": str(approval.id),
        }
        assert "It looks like" not in str(audit.after) + str(audit.before) + audit.reason
        assert not OutboxEvent.objects.filter(event_type="RequestRejected").exists()

    def test_missing_reason_or_message_is_refused(self, requester_ctx, system_ctx, pastor_ctx):
        req = _awaiting(requester_ctx, system_ctx)
        with pytest.raises(ValueError):
            reject_request(
                pastor_ctx, request_id=req.id, route="pastoral", reason_code="", message=""
            )

    def test_wrong_role_is_denied(self, requester_ctx, system_ctx, director_ctx):
        req = _awaiting(requester_ctx, system_ctx)
        with pytest.raises(PermissionDenied):
            reject_request(
                director_ctx,
                request_id=req.id,
                route="pastoral",
                reason_code="another_reason",
                message="Sorry",
            )

    def test_blocked_while_impersonating(self, requester_ctx, system_ctx, board_rep_ctx):
        req = _awaiting(requester_ctx, system_ctx)
        with pytest.raises(ImpersonationBlocked):
            reject_request(
                _impersonating(board_rep_ctx),
                request_id=req.id,
                route="board",
                reason_code="another_reason",
                message="Sorry",
            )


# ------------------------------------------------------------------------------------------
# Concurrency (Q-153: the first recorded decision settles it)
# ------------------------------------------------------------------------------------------
@pytest.mark.django_db(transaction=True)
def test_two_approvers_deciding_at_once_only_one_wins(
    requester_ctx, system_ctx, pastor_ctx, board_rep_ctx
):
    req = _awaiting(requester_ctx, system_ctx)
    results: dict[str, str] = {}
    barrier = threading.Barrier(2)

    def _approve():
        from django.db import connection

        barrier.wait()
        try:
            approve_request(pastor_ctx, request_id=req.id, route="pastoral")
            results["approve"] = "ok"
        except ValueError as exc:
            results["approve"] = str(exc)
        finally:
            connection.close()

    def _reject():
        from django.db import connection

        barrier.wait()
        try:
            reject_request(
                board_rep_ctx,
                request_id=req.id,
                route="board",
                reason_code="another_reason",
                message="Sorry",
            )
            results["reject"] = "ok"
        except ValueError as exc:
            results["reject"] = str(exc)
        finally:
            connection.close()

    t1 = threading.Thread(target=_approve)
    t2 = threading.Thread(target=_reject)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    oks = [v for v in results.values() if v == "ok"]
    assert len(oks) == 1, results
    assert Approval.objects.filter(request_id=req.id).count() == 1
    assert (
        AuditEvent.objects.filter(action__in=["request.approved", "request.rejected"]).count() == 1
    )

    # This is a `transaction=True` test (real commits, so the row lock genuinely serializes
    # the two threads): every job this test deferred (the duplicate-check job `_awaiting`'s
    # `submit_request` call always enqueues, the held-effects job the winning decision
    # defers, ...) was committed for real and would otherwise survive this test's own DB
    # flush -- an unrelated later test's own `run_due_jobs_now()` would then pick up a stale
    # `complete_intake_checks` job for an already-decided request id (`wrong_state`) or a
    # stale delivery pointed at an already-flushed row. Discard them without running them:
    # this test has already made and checked every assertion it needs to.
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM procrastinate_jobs WHERE status = 'todo'")


# ------------------------------------------------------------------------------------------
# review_urgency
# ------------------------------------------------------------------------------------------
class TestReviewUrgency:
    def test_certify_after_approval_becomes_urgent_approval_once(
        self, requester_ctx, system_ctx, pastor_ctx, board_rep_ctx
    ):
        req = _urgent_awaiting(requester_ctx, system_ctx)
        approval = approve_request(board_rep_ctx, request_id=req.id, route="board")
        request_row = review_urgency(pastor_ctx, request_id=req.id, certify=True)
        assert request_row.urgency_status == UrgencyStatus.CERTIFIED.value
        event = OutboxEvent.objects.get(event_type="UrgencyCertified")
        assert event.payload == {"request_id": str(req.id)}
        alert = OutboxEvent.objects.get(event_type="RequestUrgentApproval")
        assert alert.payload == {"request_id": str(req.id), "approval_id": str(approval.id)}

    def test_decline_urgency_not_certified_is_immediate(
        self, requester_ctx, system_ctx, pastor_ctx
    ):
        req = _urgent_awaiting(requester_ctx, system_ctx)
        review_urgency(pastor_ctx, request_id=req.id, certify=False)
        event = OutboxEvent.objects.get(event_type="UrgencyNotCertified")
        assert event.payload == {"request_id": str(req.id)}

    def test_only_a_pastor_may_review(self, requester_ctx, system_ctx, board_rep_ctx):
        req = _urgent_awaiting(requester_ctx, system_ctx)
        with pytest.raises(PermissionDenied):
            review_urgency(board_rep_ctx, request_id=req.id, certify=True)


# ------------------------------------------------------------------------------------------
# Reconsideration
# ------------------------------------------------------------------------------------------
class TestReconsideration:
    def _rejected(self, requester_ctx, system_ctx, pastor_ctx):
        req = _awaiting(requester_ctx, system_ctx)
        approval = reject_request(
            pastor_ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="another_reason",
            message="Sorry",
        )
        req.refresh_from_db()
        return req, approval

    def test_requester_requests_reconsideration(self, requester_ctx, system_ctx, pastor_ctx):
        req, _approval = self._rejected(requester_ctx, system_ctx, pastor_ctx)
        from ham.authz.context import RequesterContext

        recon_ctx = RequesterContext(request_id=req.id)
        request_reconsideration(recon_ctx, note="Please look again")
        req.refresh_from_db()
        assert req.status == RequestStatus.RECONSIDERATION_PENDING.value
        recon = Reconsideration.objects.get(request_id=req.id)
        assert recon.requested_via == "secure_page"
        assert recon.route == ApprovalRoute.PASTORAL.value
        assert OutboxEvent.objects.get(event_type="ReconsiderationRequested").payload == {
            "request_id": str(req.id),
            "reconsideration_id": str(recon.id),
            "route": "pastoral",
            "via": "secure_page",
        }

    def test_second_reconsideration_request_is_refused(self, requester_ctx, system_ctx, pastor_ctx):
        req, _ = self._rejected(requester_ctx, system_ctx, pastor_ctx)
        from ham.authz.context import RequesterContext

        recon_ctx = RequesterContext(request_id=req.id)
        request_reconsideration(recon_ctx)
        with pytest.raises(ValueError):
            request_reconsideration(recon_ctx)

    def test_director_records_reconsideration_by_phone(
        self, requester_ctx, system_ctx, pastor_ctx, director_ctx
    ):
        req, _ = self._rejected(requester_ctx, system_ctx, pastor_ctx)
        record_reconsideration_by_phone(director_ctx, request_id=req.id, note="called in")
        recon = Reconsideration.objects.get(request_id=req.id)
        assert recon.requested_via == "phone"
        assert recon.recorded_by_user_id == director_ctx.user_id

    def test_only_director_or_ad_may_record_phone_reconsideration(
        self, requester_ctx, system_ctx, pastor_ctx
    ):
        req, _ = self._rejected(requester_ctx, system_ctx, pastor_ctx)
        with pytest.raises(PermissionDenied):
            record_reconsideration_by_phone(pastor_ctx, request_id=req.id)

    def test_original_pastor_decides_reconsideration(self, requester_ctx, system_ctx, pastor_ctx):
        req, _ = self._rejected(requester_ctx, system_ctx, pastor_ctx)
        from ham.authz.context import RequesterContext

        request_reconsideration(RequesterContext(request_id=req.id))
        approval = decide_reconsideration(
            pastor_ctx, request_id=req.id, approve=True, reason="Looked again, approved"
        )
        req.refresh_from_db()
        assert req.status == RequestStatus.APPROVED.value
        assert approval.stage == ApprovalStage.RECONSIDERATION.value

    def test_another_pastor_needs_explicit_takeover(self, requester_ctx, system_ctx, make_user):
        # An active-pastor `RoleAssignment` row is needed here: the original decider must
        # read as a *currently active* pastor, or `may_decide_reconsideration` waves any
        # other pastor straight through (Q-157's "the original pastor lost the role" branch).
        pastor_ctx = _active_pastor_ctx(make_user)
        req, _ = self._rejected(requester_ctx, system_ctx, pastor_ctx)
        from ham.authz.context import RequesterContext

        request_reconsideration(RequesterContext(request_id=req.id))
        other_pastor = _active_pastor_ctx(make_user)
        with pytest.raises(ValueError, match="not_your_reconsideration"):
            decide_reconsideration(other_pastor, request_id=req.id, approve=True, reason="ok")
        approval = decide_reconsideration(
            other_pastor,
            request_id=req.id,
            approve=True,
            reason="ok",
            take_over=True,
        )
        assert str(approval.took_over_from_user_id) == str(pastor_ctx.user_id)
        assert approval.unavailable_confirmed is True

    def test_reconsider_reject_closes_the_request(self, requester_ctx, system_ctx, pastor_ctx):
        req, _ = self._rejected(requester_ctx, system_ctx, pastor_ctx)
        from ham.authz.context import RequesterContext

        request_reconsideration(RequesterContext(request_id=req.id))
        decide_reconsideration(
            pastor_ctx,
            request_id=req.id,
            approve=False,
            reason="Still no",
            reason_code="another_reason",
        )
        req.refresh_from_db()
        assert req.status == RequestStatus.REJECTED.value
        assert req.closed_at is not None


# ------------------------------------------------------------------------------------------
# finalize_rejection + hourly job
# ------------------------------------------------------------------------------------------
class TestFinalizeRejection:
    def test_finalize_before_deadline_is_refused(self, requester_ctx, system_ctx, pastor_ctx):
        req = _awaiting(requester_ctx, system_ctx)
        reject_request(
            pastor_ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="another_reason",
            message="Sorry",
        )
        with pytest.raises(ValueError, match="deadline_not_reached"):
            finalize_rejection(system_ctx, request_id=req.id)

    def test_finalize_after_deadline_closes_the_request(
        self, requester_ctx, system_ctx, pastor_ctx
    ):
        req = _awaiting(requester_ctx, system_ctx)
        reject_request(
            pastor_ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="another_reason",
            message="Sorry",
        )
        req.refresh_from_db()
        set_clock(FixedClock(req.reconsideration_deadline_at + timedelta(seconds=1)))
        finalize_rejection(system_ctx, request_id=req.id)
        req.refresh_from_db()
        assert req.status == RequestStatus.REJECTED.value
        assert req.closed_at is not None
        assert OutboxEvent.objects.filter(event_type="RequestRejectionFinalized").count() == 1

    def test_hourly_job_finalizes_every_eligible_request(
        self, requester_ctx, system_ctx, pastor_ctx
    ):
        from ham.requests.jobs import finalize_rejections

        req = _awaiting(requester_ctx, system_ctx)
        reject_request(
            pastor_ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="another_reason",
            message="Sorry",
        )
        req.refresh_from_db()
        set_clock(FixedClock(req.reconsideration_deadline_at + timedelta(hours=1)))
        finalize_rejections(0)
        req.refresh_from_db()
        assert req.closed_at is not None

    def test_finalize_is_idempotent(self, requester_ctx, system_ctx, pastor_ctx):
        from ham.requests.jobs import finalize_rejections

        req = _awaiting(requester_ctx, system_ctx)
        reject_request(
            pastor_ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="another_reason",
            message="Sorry",
        )
        req.refresh_from_db()
        set_clock(FixedClock(req.reconsideration_deadline_at + timedelta(hours=1)))
        finalize_rejections(0)
        finalize_rejections(0)  # no-op the second time (nothing eligible any more)
        assert AuditEvent.objects.filter(action="request.rejection_finalized").count() == 1


# ------------------------------------------------------------------------------------------
# record_decision_phoned / change_category
# ------------------------------------------------------------------------------------------
class TestPhoneAndCategory:
    def test_record_decision_phoned_sets_the_once_fields(
        self, requester_ctx, system_ctx, pastor_ctx, director_ctx
    ):
        req = _no_email_awaiting(requester_ctx, system_ctx, director_ctx)
        approve_request(pastor_ctx, request_id=req.id, route="pastoral")
        record_decision_phoned(director_ctx, request_id=req.id)
        approval = Approval.objects.get(request_id=req.id)
        assert approval.requester_phoned_at is not None
        assert approval.requester_phoned_by_user_id == director_ctx.user_id
        with pytest.raises(ValueError):
            record_decision_phoned(director_ctx, request_id=req.id)

    def test_change_category_is_allowed_while_impersonating(
        self, requester_ctx, system_ctx, director_ctx
    ):
        req = _awaiting(requester_ctx, system_ctx)
        change_category(_impersonating(director_ctx), request_id=req.id, need_category="electrical")
        req.refresh_from_db()
        assert req.need_category == "electrical"

    def test_change_category_wrong_role_is_denied(self, requester_ctx, system_ctx, pastor_ctx):
        req = _awaiting(requester_ctx, system_ctx)
        with pytest.raises(PermissionDenied):
            change_category(pastor_ctx, request_id=req.id, need_category="electrical")


# ------------------------------------------------------------------------------------------
# undo_decision (Q-156/Q-176)
# ------------------------------------------------------------------------------------------
class TestCancelExtension:
    """Q-165: after a decision, only "requester withdrew" from APPROVED/RECONSIDERATION_
    PENDING, and only once that decision can no longer be undone."""

    def test_requester_withdrew_from_approved_is_allowed_after_the_undo_window(
        self, requester_ctx, system_ctx, pastor_ctx, director_ctx
    ):
        req = _awaiting(requester_ctx, system_ctx)
        approval = approve_request(pastor_ctx, request_id=req.id, route="pastoral")
        set_clock(
            FixedClock(
                approval.decided_at + RULES.approvals.DECISION_UNDO_WINDOW + timedelta(seconds=1)
            )
        )
        cancel_request(director_ctx, request_id=req.id, reason_code="requester_withdrew")
        req.refresh_from_db()
        assert req.status == RequestStatus.CANCELLED.value

    def test_cancel_is_refused_while_the_decision_can_still_be_undone(
        self, requester_ctx, system_ctx, pastor_ctx, director_ctx
    ):
        req = _awaiting(requester_ctx, system_ctx)
        approve_request(pastor_ctx, request_id=req.id, route="pastoral")
        with pytest.raises(ValueError, match="decision_undo_window_open"):
            cancel_request(director_ctx, request_id=req.id, reason_code="requester_withdrew")

    def test_only_requester_withdrew_is_allowed_after_a_decision(
        self, requester_ctx, system_ctx, pastor_ctx, director_ctx
    ):
        req = _awaiting(requester_ctx, system_ctx)
        approval = approve_request(pastor_ctx, request_id=req.id, route="pastoral")
        set_clock(
            FixedClock(
                approval.decided_at + RULES.approvals.DECISION_UNDO_WINDOW + timedelta(seconds=1)
            )
        )
        with pytest.raises(ValueError, match="reason_not_allowed"):
            cancel_request(director_ctx, request_id=req.id, reason_code="spam")


class TestUndoDecision:
    def test_decider_can_undo_within_the_window(self, requester_ctx, system_ctx, pastor_ctx):
        req = _awaiting(requester_ctx, system_ctx)
        approval = approve_request(pastor_ctx, request_id=req.id, route="pastoral")
        undo_decision(pastor_ctx, approval_id=approval.id)
        approval.refresh_from_db()
        req.refresh_from_db()
        assert approval.undone_at is not None
        assert approval.undone_by_user_id == pastor_ctx.user_id
        assert req.status == RequestStatus.AWAITING_APPROVAL.value
        assert OutboxEvent.objects.get(event_type="RequestDecisionUndone").payload == {
            "request_id": str(req.id),
            "approval_id": str(approval.id),
            "stage": "initial",
        }

    def test_another_user_cannot_undo(self, requester_ctx, system_ctx, pastor_ctx):
        req = _awaiting(requester_ctx, system_ctx)
        approval = approve_request(pastor_ctx, request_id=req.id, route="pastoral")
        other_pastor = actor_ctx(roles=frozenset({roles.PASTOR}))
        with pytest.raises(ValueError, match="not_the_decider"):
            undo_decision(other_pastor, approval_id=approval.id)

    def test_undo_after_the_window_is_refused(self, requester_ctx, system_ctx, pastor_ctx):
        req = _awaiting(requester_ctx, system_ctx)
        approval = approve_request(pastor_ctx, request_id=req.id, route="pastoral")
        set_clock(
            FixedClock(
                approval.decided_at + RULES.approvals.DECISION_UNDO_WINDOW + timedelta(seconds=1)
            )
        )
        with pytest.raises(ValueError, match="undo_window_passed"):
            undo_decision(pastor_ctx, approval_id=approval.id)

    def test_re_deciding_after_undo_is_allowed(
        self, requester_ctx, system_ctx, pastor_ctx, board_rep_ctx
    ):
        req = _awaiting(requester_ctx, system_ctx)
        approval = approve_request(pastor_ctx, request_id=req.id, route="pastoral")
        undo_decision(pastor_ctx, approval_id=approval.id)
        second = reject_request(
            board_rep_ctx,
            request_id=req.id,
            route="board",
            reason_code="another_reason",
            message="Sorry",
        )
        assert second.id != approval.id
        assert (
            Approval.objects.filter(request_id=req.id, stage=ApprovalStage.INITIAL.value).count()
            == 2
        )

    def test_reject_undo_clears_the_reconsideration_deadline(
        self, requester_ctx, system_ctx, pastor_ctx
    ):
        req = _awaiting(requester_ctx, system_ctx)
        approval = reject_request(
            pastor_ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="another_reason",
            message="Sorry",
        )
        undo_decision(pastor_ctx, approval_id=approval.id)
        req.refresh_from_db()
        assert req.status == RequestStatus.AWAITING_APPROVAL.value
        assert req.reconsideration_deadline_at is None


# ------------------------------------------------------------------------------------------
# Held effects (approvals-contracts.md §4)
# ------------------------------------------------------------------------------------------
class TestHeldEffects:
    def test_effects_release_when_not_undone(self, requester_ctx, system_ctx, pastor_ctx):
        req = _awaiting(requester_ctx, system_ctx)
        approval = approve_request(pastor_ctx, request_id=req.id, route="pastoral")
        run_held_decision_effects(approval.id)
        approval.refresh_from_db()
        assert approval.effects_ran_at is not None
        event = OutboxEvent.objects.get(event_type="RequestApproved")
        assert event.payload == {
            "request_id": str(req.id),
            "stage": "initial",
            "route": "pastoral",
            "urgent_approval": False,
        }

    def test_effects_do_not_release_when_undone(self, requester_ctx, system_ctx, pastor_ctx):
        req = _awaiting(requester_ctx, system_ctx)
        approval = approve_request(pastor_ctx, request_id=req.id, route="pastoral")
        undo_decision(pastor_ctx, approval_id=approval.id)
        run_held_decision_effects(approval.id)
        approval.refresh_from_db()
        assert approval.effects_ran_at is not None
        assert not OutboxEvent.objects.filter(event_type="RequestApproved").exists()

    def test_held_effects_job_is_idempotent(self, requester_ctx, system_ctx, pastor_ctx):
        req = _awaiting(requester_ctx, system_ctx)
        approval = approve_request(pastor_ctx, request_id=req.id, route="pastoral")
        run_held_decision_effects(approval.id)
        run_held_decision_effects(approval.id)
        assert OutboxEvent.objects.filter(event_type="RequestApproved").count() == 1

    def test_held_effects_closes_open_questions(
        self, requester_ctx, system_ctx, pastor_ctx, director_ctx
    ):
        from ham.requests.models import RequestQuestion

        req = _awaiting(requester_ctx, system_ctx)
        RequestQuestion.objects.create(
            request=req, asked_by_user_id=director_ctx.user_id, asked_at=clock_now(), question="?"
        )
        approval = approve_request(pastor_ctx, request_id=req.id, route="pastoral")
        run_held_decision_effects(approval.id)
        question = RequestQuestion.objects.get(request=req)
        assert question.closed_at is not None
        assert question.close_reason == "request_closed"

    def test_held_effects_job_is_deferred_for_effective_at(
        self, requester_ctx, system_ctx, pastor_ctx
    ):
        from django.db import connection

        req = _awaiting(requester_ctx, system_ctx)
        approval = approve_request(pastor_ctx, request_id=req.id, route="pastoral")
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT scheduled_at FROM procrastinate_jobs WHERE task_name = %s "
                "AND args->>'approval_id' = %s",
                ["requests.run_held_decision_effects", str(approval.id)],
            )
            row = cursor.fetchone()
        assert row is not None
        assert row[0] == approval.effective_at


# ------------------------------------------------------------------------------------------
# PII-free audit/outbox (broad sweep across every command exercised above)
# ------------------------------------------------------------------------------------------
def test_no_pii_in_any_audit_or_outbox_row(requester_ctx, system_ctx, pastor_ctx):
    req = _awaiting(requester_ctx, system_ctx)
    approve_request(pastor_ctx, request_id=req.id, route="pastoral")
    from ham.requests.models import Requester

    requester = Requester.objects.get(request=req)
    forbidden = [requester.full_name, requester.phone]
    if requester.email:
        forbidden.append(requester.email)
    for event in AuditEvent.objects.all():
        blob = f"{event.before}{event.after}{event.context}{event.reason}"
        for value in forbidden:
            assert value not in blob
    for event in OutboxEvent.objects.all():
        blob = str(event.payload)
        for value in forbidden:
            assert value not in blob
