"""ham.notifications.services: Inbox queries (Needs response / Updates), read/acknowledge, the
urgent-banner query, and the urgent-override-of-preference contract (§10, §35, Q-123)."""

from __future__ import annotations

import uuid

import pytest

from ham.audit.models import AuditEvent
from ham.authz import roles
from ham.authz.commands import ImpersonationBlocked, PermissionDenied
from ham.authz.context import ActorContext
from ham.notifications.attention import (
    AttentionItem,
    register_attention_provider,
    unregister_attention_provider,
)
from ham.notifications.models import Notification
from ham.notifications.services import (
    acknowledge_notification,
    mark_read,
    needs_response_count,
    needs_response_for,
    unread_update_count,
    updates_for,
    urgent_banner_for,
)
from ham.platform.clock import FixedClock, set_clock
from ham.platform.clock import now as clock_now

pytestmark = pytest.mark.django_db


def _ctx(user_id, **overrides) -> ActorContext:
    return ActorContext(
        user_id=user_id,
        real_user_id=None,
        roles=frozenset({roles.PASTOR}),
        is_active=True,
        mfa_satisfied=True,
        **overrides,
    )


def _notification(recipient_id, **kwargs) -> Notification:
    defaults = dict(
        recipient_user_id=recipient_id,
        kind="test",
        subject_type="request",
        subject_id=uuid.uuid4(),
        title="Something needs your attention",
    )
    defaults.update(kwargs)
    return Notification.objects.create(**defaults)


class TestNeedsResponse:
    def test_empty_when_no_providers(self):
        assert needs_response_for(_ctx(uuid.uuid4())) == []
        assert needs_response_count(_ctx(uuid.uuid4())) == 0

    def test_muted_rows_are_shown_but_excluded_from_the_count(self):
        def provider(ctx):
            return [
                AttentionItem(kind="a", title="Waiting for a decision (3)", url="/x", count=3),
                AttentionItem(
                    kind="b",
                    title="Waiting for a decision (owner: pastors/Board) (3)",
                    url="/x",
                    count=3,
                    muted=True,
                ),
            ]

        register_attention_provider(provider)
        try:
            ctx = _ctx(uuid.uuid4())
            items = needs_response_for(ctx)
            assert len(items) == 2  # both shown
            assert needs_response_count(ctx) == 3  # only the unmuted row counts
        finally:
            unregister_attention_provider(provider)


class TestUpdates:
    def test_only_this_recipients_notifications_newest_first(self):
        mine = uuid.uuid4()
        other = uuid.uuid4()
        n1 = _notification(mine, kind="first")
        n2 = _notification(mine, kind="second")
        _notification(other, kind="not-mine")
        rows = updates_for(_ctx(mine))
        assert [n.id for n in rows] == [n2.id, n1.id]

    def test_unread_count(self):
        mine = uuid.uuid4()
        _notification(mine)
        _notification(mine, read_at=clock_now())
        assert unread_update_count(_ctx(mine)) == 1


class TestMarkRead:
    def test_marks_own_notification_read(self):
        mine = uuid.uuid4()
        notification = _notification(mine)
        result = mark_read(_ctx(mine), notification.id)
        assert result is not None
        notification.refresh_from_db()
        assert notification.read_at is not None

    def test_cannot_mark_someone_elses_notification_read(self):
        mine = uuid.uuid4()
        other = uuid.uuid4()
        notification = _notification(other)
        result = mark_read(_ctx(mine), notification.id)
        assert result is None
        notification.refresh_from_db()
        assert notification.read_at is None

    def test_idempotent(self):
        mine = uuid.uuid4()
        notification = _notification(mine)
        mark_read(_ctx(mine), notification.id)
        first_read_at = Notification.objects.get(pk=notification.id).read_at
        mark_read(_ctx(mine), notification.id)
        second_read_at = Notification.objects.get(pk=notification.id).read_at
        assert first_read_at == second_read_at


class TestUrgentBanner:
    def test_none_when_nothing_urgent(self):
        mine = uuid.uuid4()
        _notification(mine)  # ordinary update, not urgent
        assert urgent_banner_for(_ctx(mine)) is None

    def test_shows_an_unacknowledged_urgent_requires_ack_notification(self):
        mine = uuid.uuid4()
        urgent = _notification(mine, urgent=True, requires_ack=True)
        assert urgent_banner_for(_ctx(mine)).id == urgent.id

    def test_stops_showing_once_acknowledged(self):
        mine = uuid.uuid4()
        urgent = _notification(mine, urgent=True, requires_ack=True)
        acknowledge_notification(_ctx(mine), notification_id=urgent.id)
        assert urgent_banner_for(_ctx(mine)) is None

    def test_urgent_without_requires_ack_is_not_a_banner(self):
        # e.g. a non-urgent-flagged update that just happens to have urgent=True set wrong is
        # not this test's concern; this asserts requires_ack, not urgent, gates the banner.
        mine = uuid.uuid4()
        _notification(mine, urgent=True, requires_ack=False)
        assert urgent_banner_for(_ctx(mine)) is None


class TestAcknowledge:
    def test_recipient_can_acknowledge(self):
        mine = uuid.uuid4()
        urgent = _notification(mine, urgent=True, requires_ack=True)
        result = acknowledge_notification(_ctx(mine), notification_id=urgent.id)
        assert result.acknowledged_at is not None

    def test_writes_exactly_one_audit_event(self):
        mine = uuid.uuid4()
        urgent = _notification(mine, urgent=True, requires_ack=True)
        acknowledge_notification(_ctx(mine), notification_id=urgent.id)
        events = AuditEvent.objects.filter(action="notification.acknowledged")
        assert events.count() == 1
        event = events.get()
        assert event.target_id == str(urgent.id)
        assert event.actor_user_id == mine

    def test_someone_elses_notification_is_denied(self):
        mine = uuid.uuid4()
        other = uuid.uuid4()
        urgent = _notification(other, urgent=True, requires_ack=True)
        with pytest.raises(PermissionDenied):
            acknowledge_notification(_ctx(mine), notification_id=urgent.id)
        urgent.refresh_from_db()
        assert urgent.acknowledged_at is None

    def test_a_denied_attempt_is_not_audited_as_noise(self):
        # notification.acknowledge is not in _AUDITED_ON_DENIAL (an ordinary "not your
        # notification" denial, unlike privileged-action denials elsewhere in the matrix).
        mine = uuid.uuid4()
        other = uuid.uuid4()
        urgent = _notification(other, urgent=True, requires_ack=True)
        with pytest.raises(PermissionDenied):
            acknowledge_notification(_ctx(mine), notification_id=urgent.id)
        assert not AuditEvent.objects.filter(action="authz.denied").exists()

    def test_blocked_while_impersonating(self):
        mine = uuid.uuid4()
        urgent = _notification(mine, urgent=True, requires_ack=True)
        ctx = _ctx(mine, impersonation_id=uuid.uuid4())
        with pytest.raises(ImpersonationBlocked):
            acknowledge_notification(ctx, notification_id=urgent.id)
        urgent.refresh_from_db()
        assert urgent.acknowledged_at is None

    def test_idempotent_does_not_move_the_timestamp(self):
        mine = uuid.uuid4()
        urgent = _notification(mine, urgent=True, requires_ack=True)
        set_clock(FixedClock(clock_now()))
        acknowledge_notification(_ctx(mine), notification_id=urgent.id)
        first = Notification.objects.get(pk=urgent.id).acknowledged_at
        acknowledge_notification(_ctx(mine), notification_id=urgent.id)
        second = Notification.objects.get(pk=urgent.id).acknowledged_at
        assert first == second

    def test_unknown_notification_id_raises_without_audit_event(self):
        mine = uuid.uuid4()
        with pytest.raises(ValueError):
            acknowledge_notification(_ctx(mine), notification_id=uuid.uuid4())
        assert not AuditEvent.objects.filter(action="notification.acknowledged").exists()
