"""S2.2: `ham.requests.services` (intake.md §10 S2.2). State transitions through the
services, audit/outbox PII-absence, reveal logging per role, the duplicate job, the phone-
check path.
"""

from __future__ import annotations

import uuid

import pytest

from ham.audit.models import AuditEvent
from ham.authz.commands import ImpersonationBlocked, PermissionDenied
from ham.outbox.models import OutboxEvent
from ham.requests.models import Requester, RequestMatch
from ham.requests.services import (
    RevealedRequesterPII,
    cancel_request,
    complete_intake_checks,
    reveal_requester_pii,
    submit_request,
    verify_by_phone,
)
from ham.requests.states import RequestStatus

from .conftest import actor_ctx, make_payload, no_email_payload

pytestmark = pytest.mark.django_db


# --------------------------------------------------------------------------------------
# request.submit
# --------------------------------------------------------------------------------------
class TestSubmitRequest:
    def test_verified_email_submission_lands_in_submitted(self, requester_ctx):
        req = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(),
        )
        assert req.status == RequestStatus.SUBMITTED.value
        assert req.reference_number > 0
        assert Requester.objects.get(request=req).email == "jane@example.org"

    def test_no_email_submission_lands_in_needs_phone_check(self, requester_ctx):
        req = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=no_email_payload(),
        )
        assert req.status == RequestStatus.NEEDS_PHONE_CHECK.value
        assert Requester.objects.get(request=req).email is None

    def test_missing_certification_statement_is_refused(self, requester_ctx):
        payload = make_payload(attested_statements=("true_to_knowledge",))
        with pytest.raises(ValueError):
            submit_request(
                requester_ctx, draft_id=uuid.uuid4(), verification_id=uuid.uuid4(), payload=payload
            )

    def test_urgent_without_justification_is_refused(self, requester_ctx):
        payload = make_payload(urgent_requested=True, urgency_justification="")
        with pytest.raises(ValueError):
            submit_request(
                requester_ctx, draft_id=uuid.uuid4(), verification_id=uuid.uuid4(), payload=payload
            )

    def test_audits_actor_type_requester(self, requester_ctx):
        req = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(),
        )
        event = AuditEvent.objects.get(target_id=str(req.id), action="request.submitted")
        assert event.actor_type == "requester"
        assert event.actor_user_id is None
        assert event.project_id == req.id

    def test_emits_request_submitted_ids_only(self, requester_ctx):
        req = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(),
        )
        event = OutboxEvent.objects.get(event_type="RequestSubmitted", aggregate_id=req.id)
        assert set(event.payload) == {"request_id", "source", "urgent"}
        assert event.payload["request_id"] == str(req.id)

    def test_no_pii_in_audit_before_after_or_outbox_payload(self, requester_ctx):
        req = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(),
        )
        for event in AuditEvent.objects.filter(project_id=req.id):
            for blob in (event.before, event.after, event.context):
                text = str(blob)
                assert "jane@example.org" not in text
                assert "Jane Test" not in text
                assert "Main St" not in text
        for event in OutboxEvent.objects.filter(aggregate_id=req.id):
            text = str(event.payload)
            assert "jane@example.org" not in text
            assert "Jane Test" not in text
            assert "Main St" not in text


# --------------------------------------------------------------------------------------
# system.request.complete_intake_checks (the duplicate job)
# --------------------------------------------------------------------------------------
class TestCompleteIntakeChecks:
    def test_moves_submitted_to_awaiting_approval(self, requester_ctx, system_ctx):
        req = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(),
        )
        result = complete_intake_checks(system_ctx, request_id=req.id)
        assert result.status == RequestStatus.AWAITING_APPROVAL.value

    def test_flags_a_same_address_duplicate(self, requester_ctx, system_ctx):
        first = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(),
        )
        complete_intake_checks(system_ctx, request_id=first.id)

        second = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(full_name="Someone Else", email="someone@example.org"),
        )
        complete_intake_checks(system_ctx, request_id=second.id)

        match = RequestMatch.objects.get(request=second, prior_request=first)
        assert "address" in match.reasons
        assert AuditEvent.objects.filter(
            target_id=str(second.id), action="request.duplicates_flagged"
        ).exists()
        assert AuditEvent.objects.filter(
            target_id=str(second.id), action="request.status_changed"
        ).exists()

    def test_a_match_never_changes_the_normal_status_move(self, requester_ctx, system_ctx):
        first = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(),
        )
        complete_intake_checks(system_ctx, request_id=first.id)
        second = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(full_name="Someone Else", email="someone@example.org"),
        )
        result = complete_intake_checks(system_ctx, request_id=second.id)
        assert result.status == RequestStatus.AWAITING_APPROVAL.value

    def test_refuses_from_the_wrong_status(self, requester_ctx, system_ctx):
        req = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(),
        )
        complete_intake_checks(system_ctx, request_id=req.id)
        with pytest.raises(ValueError):
            complete_intake_checks(system_ctx, request_id=req.id)

    def test_duplicate_reasons_never_reach_the_outbox_payload(self, requester_ctx, system_ctx):
        first = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(),
        )
        complete_intake_checks(system_ctx, request_id=first.id)
        second = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(full_name="Someone Else", email="someone@example.org"),
        )
        complete_intake_checks(system_ctx, request_id=second.id)
        for event in OutboxEvent.objects.filter(aggregate_id=second.id):
            assert "address" not in str(event.payload)
            assert "email" not in str(event.payload)


# --------------------------------------------------------------------------------------
# request.contact_verify_phone (Q-025 "verified by phone call")
# --------------------------------------------------------------------------------------
class TestVerifyByPhone:
    def test_moves_needs_phone_check_to_submitted_and_enqueues_checks(
        self, requester_ctx, director_ctx
    ):
        req = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=no_email_payload(),
        )
        result = verify_by_phone(director_ctx, request_id=req.id)
        assert result.status == RequestStatus.SUBMITTED.value

    def test_blocked_while_impersonating(self, requester_ctx, director_ctx):
        req = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=no_email_payload(),
        )
        impersonating = actor_ctx(
            roles=frozenset({"HAM_DIRECTOR"}),
            real_user_id=uuid.uuid4(),
            impersonation_id=uuid.uuid4(),
        )
        with pytest.raises(ImpersonationBlocked):
            verify_by_phone(impersonating, request_id=req.id)

    def test_pastor_may_not_verify_by_phone(self, requester_ctx, pastor_ctx):
        req = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=no_email_payload(),
        )
        with pytest.raises(PermissionDenied):
            verify_by_phone(pastor_ctx, request_id=req.id)

    def test_wrong_status_is_refused(self, requester_ctx, director_ctx):
        req = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(),
        )
        with pytest.raises(ValueError):
            verify_by_phone(director_ctx, request_id=req.id)


# --------------------------------------------------------------------------------------
# request.cancel, including Q-140
# --------------------------------------------------------------------------------------
class TestCancelRequest:
    def test_cancel_with_spam_reason(self, requester_ctx, director_ctx):
        req = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(),
        )
        result = cancel_request(director_ctx, request_id=req.id, reason_code="spam")
        assert result.status == RequestStatus.CANCELLED.value
        assert result.cancel_reason_code == "spam"
        assert result.closed_at is not None
        assert result.requester_access_ends_at is not None

    def test_couldnt_reach_them_only_from_needs_phone_check(
        self, requester_ctx, director_ctx, assistant_director_ctx
    ):
        no_email = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=no_email_payload(),
        )
        result = cancel_request(
            director_ctx, request_id=no_email.id, reason_code="couldnt_reach_them"
        )
        assert result.status == RequestStatus.CANCELLED.value

        submitted = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(full_name="Other Person", email="other@example.org"),
        )
        with pytest.raises(ValueError):
            cancel_request(
                assistant_director_ctx, request_id=submitted.id, reason_code="couldnt_reach_them"
            )

    def test_pastor_may_not_cancel(self, requester_ctx, pastor_ctx):
        req = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(),
        )
        with pytest.raises(PermissionDenied):
            cancel_request(pastor_ctx, request_id=req.id, reason_code="spam")

    def test_blocked_while_impersonating(self, requester_ctx):
        req = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(),
        )
        impersonating = actor_ctx(
            roles=frozenset({"HAM_DIRECTOR"}),
            real_user_id=uuid.uuid4(),
            impersonation_id=uuid.uuid4(),
        )
        with pytest.raises(ImpersonationBlocked):
            cancel_request(impersonating, request_id=req.id, reason_code="spam")


# --------------------------------------------------------------------------------------
# requester_pii.reveal (Q-009, Q-024, Q-081, Q-122, Q-125)
# --------------------------------------------------------------------------------------
class TestRevealRequesterPII:
    def _submitted(self, requester_ctx):
        return submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(),
        )

    def test_director_not_impersonating_is_not_logged(self, requester_ctx, director_ctx):
        req = self._submitted(requester_ctx)
        before = AuditEvent.objects.filter(action="requester_pii.revealed").count()
        pii = reveal_requester_pii(director_ctx, request_id=req.id)
        assert isinstance(pii, RevealedRequesterPII)
        assert pii.full_name == "Jane Test"
        after = AuditEvent.objects.filter(action="requester_pii.revealed").count()
        assert after == before

    def test_director_impersonating_is_logged(self, requester_ctx):
        req = self._submitted(requester_ctx)
        impersonating = actor_ctx(
            roles=frozenset({"HAM_DIRECTOR"}),
            real_user_id=uuid.uuid4(),
            impersonation_id=uuid.uuid4(),
        )
        reveal_requester_pii(impersonating, request_id=req.id)
        event = AuditEvent.objects.get(action="requester_pii.revealed", target_id=str(req.id))
        assert event.actor_type == "user"
        assert event.acting_as_user_id == impersonating.user_id
        assert event.actor_user_id == impersonating.real_user_id

    @pytest.mark.parametrize("role", ["ASSISTANT_DIRECTOR", "PASTOR", "BOARD_REPRESENTATIVE"])
    def test_everyone_else_is_logged_with_field_names_not_values(self, requester_ctx, role):
        req = self._submitted(requester_ctx)
        ctx = actor_ctx(roles=frozenset({role}))
        reveal_requester_pii(ctx, request_id=req.id)
        event = AuditEvent.objects.get(action="requester_pii.revealed", target_id=str(req.id))
        assert "full_name" in event.context["fields"]
        assert "Jane Test" not in str(event.context)
        assert "jane@example.org" not in str(event.context)

    def test_administrator_is_refused_and_denial_is_audited(self, requester_ctx, administrator_ctx):
        req = self._submitted(requester_ctx)
        with pytest.raises(PermissionDenied):
            reveal_requester_pii(administrator_ctx, request_id=req.id)
        assert AuditEvent.objects.filter(
            action="authz.denied", target_id="requester_pii.reveal"
        ).exists()

    def test_a_volunteer_is_refused(self, requester_ctx):
        req = self._submitted(requester_ctx)
        ctx = actor_ctx(roles=frozenset({"VOLUNTEER"}))
        with pytest.raises(PermissionDenied):
            reveal_requester_pii(ctx, request_id=req.id)
