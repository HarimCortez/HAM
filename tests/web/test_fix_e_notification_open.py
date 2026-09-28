"""FIX-E N7 regression: `ham.web.views.notification_open` (a) must not mark a notification
read while impersonating (an Administrator browsing another person's inbox shouldn't silently
change what they see as unread), (b) must redirect to the inbox rather than 500 on a bad/
unreversable subject, and (c) `request_detail`'s `back_tab` context value must be whitelisted
against the known `requests_list` tab keys. New file per wave brief.
"""

from __future__ import annotations

import uuid

import pytest
from django.urls import reverse

from ham.authz import roles
from ham.identity.models import ImpersonationSession, RoleAssignment, SharedIdentityProfile
from ham.notifications.models import Notification
from ham.platform.clock import now as clock_now
from tests.web.test_fix_c_leadership_screens import _login, _make_request

pytestmark = pytest.mark.django_db


def _notification_for(user, *, subject_type="request", subject_id=None):
    """Builds a `Notification` row directly -- no builder for a "request" subject Update is
    wired in this slice yet (`updates_for` returns `[]`, same as `tests/web/
    test_fix_c_leadership_screens.py::test_inbox_updates_are_links_that_open_the_subject`
    already documents), so these tests exercise `notification_open` against a row shaped the
    way one eventually will be rather than skipping."""
    return Notification.objects.create(
        recipient_user_id=user.id,
        kind="request_awaiting_approval",
        subject_type=subject_type,
        subject_id=subject_id or uuid.uuid4(),
        title="A request needs review",
    )


def _impersonation_session(client, real_user, target_user):
    """Marks the current session as impersonating `target_user` -- the same shape
    `tests/web/test_impersonation_banner_shell.py::impersonating_client` uses."""
    session_row = ImpersonationSession.objects.create(
        admin_user_id=real_user.id,
        target_user_id=target_user.id,
        reason="support",
        started_at=clock_now(),
        last_activity_at=clock_now(),
    )
    session = client.session
    session["ham_impersonation_id"] = str(session_row.id)
    session["ham_mfa_satisfied"] = True
    session.save()
    return session_row


def test_notification_open_does_not_mark_read_while_impersonating(client, make_user):
    target = make_user("pastor-target@example.org")
    SharedIdentityProfile.objects.create(user=target, full_name="Target Pastor")
    RoleAssignment.objects.create(user=target, role=roles.PASTOR, granted_at=clock_now())

    admin = make_user("admin-impersonator@example.org")
    SharedIdentityProfile.objects.create(user=admin, full_name="Admin Impersonator")
    RoleAssignment.objects.create(user=admin, role=roles.ADMINISTRATOR, granted_at=clock_now())

    req = _make_request()
    notification = _notification_for(target, subject_id=req.id)
    assert notification.read_at is None

    client.force_login(admin)
    _impersonation_session(client, admin, target)

    resp = client.get(reverse("web:notification_open", args=[notification.id]), follow=False)
    assert resp.status_code == 302

    notification.refresh_from_db()
    assert notification.read_at is None  # N7: never marked read on the impersonated person's behalf


def test_notification_open_redirects_to_inbox_on_unreversable_subject(
    client, make_user, monkeypatch
):
    req = _make_request()
    user = _login(
        client, make_user, email="pastor-badsubject@example.org", full_name="P B", role="PASTOR"
    )
    notification = _notification_for(user, subject_id=req.id)

    from ham.web import views as web_views

    # A future subject_type could map to a URL name whose kwarg doesn't match "request_id" --
    # simulate that mismatch rather than waiting for one to exist for real.
    monkeypatch.setitem(
        web_views._NOTIFICATION_SUBJECT_URL_NAMES, notification.subject_type, "web:home"
    )
    resp = client.get(reverse("web:notification_open", args=[notification.id]), follow=False)
    assert resp.status_code == 302
    assert resp.url == reverse("web:inbox")


def test_notification_open_unknown_id_redirects_to_inbox(client, make_user):
    _login(client, make_user, email="pastor-noid@example.org", full_name="P N", role="PASTOR")
    resp = client.get(reverse("web:notification_open", args=[uuid.uuid4()]), follow=False)
    assert resp.status_code == 302
    assert resp.url == reverse("web:inbox")


def test_back_tab_is_whitelisted_against_known_tab_keys(client, make_user):
    req = _make_request()
    _login(
        client,
        make_user,
        email="director-backtab@example.org",
        full_name="D T",
        role="HAM_DIRECTOR",
    )

    resp = client.get(
        reverse("web:request_detail", kwargs={"request_id": req.id}), {"tab": "not-a-real-tab"}
    )
    assert resp.status_code == 200
    assert b"?tab=not-a-real-tab" not in resp.content

    resp = client.get(
        reverse("web:request_detail", kwargs={"request_id": req.id}), {"tab": "awaiting"}
    )
    assert resp.status_code == 200
    assert b"?tab=awaiting" in resp.content
