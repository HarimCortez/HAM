"""Step-2 fix round (FIX-A): L2 (scoped reveal lookup, no 500 on unknown id), L4 (spam purge
removes requester_portal link/challenge rows too; orphaned tokens are invalid, not a 500),
L7/Q-151 (an Administrator impersonating may never reveal), N8 (closed_by/awaiting_approval_at
survive a later status change).
"""

from __future__ import annotations

import uuid

import pytest

from ham.audit.models import AuditEvent
from ham.authz.commands import PermissionDenied
from ham.authz.context import SystemContext
from ham.outbox.models import OutboxEvent
from ham.platform.clock import now as clock_now
from ham.requests.models import AssistanceRequest
from ham.requests.queries import request_history
from ham.requests.services import (
    cancel_request,
    complete_intake_checks,
    purge_expired_request,
    reveal_requester_pii,
    submit_request,
)
from ham.requests.states import CancelReason

from .conftest import actor_ctx, make_payload, no_email_payload

pytestmark = pytest.mark.django_db


def _submit(requester_ctx, **overrides):
    return submit_request(
        requester_ctx,
        draft_id=uuid.uuid4(),
        verification_id=uuid.uuid4(),
        payload=make_payload(**overrides),
    )


class TestL2ScopedReveal:
    def test_unknown_id_is_permission_denied_not_500(self, director_ctx):
        with pytest.raises(PermissionDenied):
            reveal_requester_pii(director_ctx, request_id=uuid.uuid4())

    def test_pastor_cannot_reveal_a_needs_phone_check_request_by_guessing_its_id(
        self, requester_ctx, pastor_ctx
    ):
        req = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=None,
            payload=no_email_payload(),
        )
        assert req.status == "NEEDS_PHONE_CHECK"
        with pytest.raises(PermissionDenied):
            reveal_requester_pii(pastor_ctx, request_id=req.id)
        # And it isn't audited as a "revealed" (only the denial, if anything).
        assert not AuditEvent.objects.filter(
            action="requester_pii.revealed", target_id=str(req.id)
        ).exists()

    def test_director_can_still_reveal_a_needs_phone_check_request(
        self, requester_ctx, director_ctx
    ):
        req = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=None,
            payload=no_email_payload(),
        )
        pii = reveal_requester_pii(director_ctx, request_id=req.id)
        assert pii.full_name


class TestL7BlockAdministratorImpersonating:
    def test_administrator_impersonating_a_director_is_blocked(self, requester_ctx, make_user):
        req = _submit(requester_ctx)
        admin_user = make_user("admin@example.org")
        from ham.authz import roles
        from ham.identity.models import RoleAssignment

        RoleAssignment.objects.create(
            user=admin_user, role=roles.ADMINISTRATOR, granted_at=clock_now()
        )

        ctx = actor_ctx(
            roles=frozenset({roles.HAM_DIRECTOR}),
            real_user_id=admin_user.id,
            impersonation_id=uuid.uuid4(),
        )
        with pytest.raises(PermissionDenied):
            reveal_requester_pii(ctx, request_id=req.id)
        assert not AuditEvent.objects.filter(
            action="requester_pii.revealed", target_id=str(req.id)
        ).exists()
        assert AuditEvent.objects.filter(
            action="authz.denied", target_id="requester_pii.reveal"
        ).exists()

    def test_a_non_administrator_impersonating_a_director_is_unaffected(
        self, requester_ctx, make_user
    ):
        req = _submit(requester_ctx)
        from ham.authz import roles

        director_who_is_impersonating = make_user("real-director@example.org")
        from ham.identity.models import RoleAssignment

        RoleAssignment.objects.create(
            user=director_who_is_impersonating, role=roles.HAM_DIRECTOR, granted_at=clock_now()
        )

        ctx = actor_ctx(
            roles=frozenset({roles.HAM_DIRECTOR}),
            real_user_id=director_who_is_impersonating.id,
            impersonation_id=uuid.uuid4(),
        )
        pii = reveal_requester_pii(ctx, request_id=req.id)
        assert pii.full_name


class TestL4SpamPurgeRemovesLinkRows:
    def test_spam_purge_emits_requestpurged_for_the_portal_to_clean_up(self, requester_ctx):
        req = _submit(requester_ctx)
        cancel_request(
            actor_ctx(roles=frozenset({"HAM_DIRECTOR"})),
            request_id=req.id,
            reason_code=CancelReason.SPAM.value,
        )
        purge_expired_request(SystemContext(), request_id=req.id)
        assert not AssistanceRequest.objects.filter(id=req.id).exists()
        event = OutboxEvent.objects.get(event_type="RequestPurged", aggregate_id=req.id)
        assert event.payload == {"request_id": str(req.id)}


class TestN8HistorySurvivesClose:
    def test_awaiting_approval_entry_survives_a_later_cancel(self, requester_ctx, director_ctx):
        req = _submit(requester_ctx)
        complete_intake_checks(SystemContext(), request_id=req.id)
        req.refresh_from_db()
        assert req.status == "AWAITING_APPROVAL"

        cancel_request(
            director_ctx, request_id=req.id, reason_code=CancelReason.DUPLICATE_SUBMISSION.value
        )
        req.refresh_from_db()
        assert req.status == "CANCELLED"

        history = request_history(req)
        labels = [e.label for e in history]
        assert "Awaiting Approval (automatic)" in labels

    def test_closed_by_is_recorded_and_shown_in_history_actor(self, requester_ctx, director_ctx):
        req = _submit(requester_ctx)
        cancel_request(director_ctx, request_id=req.id, reason_code=CancelReason.SPAM.value)
        req.refresh_from_db()
        assert req.closed_by_user_id == director_ctx.user_id
        history = request_history(req)
        close_entries = [e for e in history if e.actor_user_id == director_ctx.user_id]
        assert close_entries
