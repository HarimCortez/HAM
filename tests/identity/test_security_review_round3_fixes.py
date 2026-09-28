"""Regression tests for the round-3 security re-review
(`scratchpad/reviews/round3.md`), adapted from the reviewer's own probe tests
(`scratchpad/test_sec_probe.py`, the "NEW" probes -- those asserted the *defect*; these assert
the fix). Harness (`fixed_clock`/`tick`/`_user`/`_enroll`/`_admin`/`_email_step`/
`_full_sign_in`/`_step_up`) mirrors that probe file and `tests/identity/
test_security_review_fixes.py` so a TOTP code is never reused across two calls in the same
test (H2 replay protection would otherwise reject the second use).
"""

from __future__ import annotations

import datetime as dt
import json
import re

import pytest
from django.core import mail
from django.test import Client, RequestFactory
from django.urls import reverse

from ham import jobs
from ham.audit.models import AuditEvent
from ham.authz import roles
from ham.identity import mfa, totp
from ham.identity.impersonation import sweep_idle_impersonation_sessions
from ham.identity.models import (
    ImpersonationSession,
    RoleAssignment,
    SharedIdentityProfile,
    User,
)
from ham.outbox.models import OutboxEvent
from ham.platform.clock import FixedClock, SystemClock, set_clock
from ham.platform.clock import now as clock_now

pytestmark = pytest.mark.django_db

CLOCK: FixedClock | None = None


@pytest.fixture(autouse=True)
def fixed_clock():
    global CLOCK
    CLOCK = FixedClock(dt.datetime.now(dt.UTC))
    set_clock(CLOCK)
    yield CLOCK
    set_clock(SystemClock())


def tick(seconds: int = 31) -> None:
    assert CLOCK is not None
    CLOCK.advance(dt.timedelta(seconds=seconds))


def _user(email: str, role: str) -> User:
    u = User.objects.create_user(email=email)
    u.first_sign_in_at = clock_now()
    u.save()
    RoleAssignment.objects.create(user=u, role=role, granted_at=clock_now())
    return u


def _enroll(u: User) -> str:
    e = mfa.start_enrollment(u)
    mfa.confirm_enrollment(u, secret=e.secret, code=totp.current_code(e.secret))
    return e.secret


def _admin(email: str) -> tuple[User, str]:
    u = _user(email, roles.ADMINISTRATOR)
    return u, _enroll(u)


def _email_step(client: Client, email: str):
    client.post(reverse("web:sign_in"), {"email": email})
    jobs.run_due_jobs_now()
    body = str(mail.outbox[-1].body)
    match = re.search(r"code is (\d{3}) (\d{3})", body)
    assert match is not None
    return client.post(reverse("web:sign_in_code"), {"code": match.group(1) + match.group(2)})


def _full_sign_in(client: Client, u: User, secret: str):
    _email_step(client, u.email)
    tick()
    r = client.post(reverse("web:sign_in_mfa"), {"code": totp.current_code(secret)})
    assert r.status_code == 302, r
    assert client.session.get("ham_mfa_satisfied") is True
    return r


def _step_up(client: Client, secret: str, kind: str):
    tick()
    r = client.post(reverse("web:step_up") + f"?kind={kind}", {"code": totp.current_code(secret)})
    assert r.status_code == 302, r.content[:300]
    return r


def _imp_setup(email: str):
    admin, secret = _admin(email)
    vol = _user("t-" + email, roles.VOLUNTEER)
    c = Client()
    _full_sign_in(c, admin, secret)
    _step_up(c, secret, "impersonation_start")
    r = c.post(reverse("web:impersonation_start", args=[vol.id]), {"reason": "help with login"})
    assert r.status_code == 302, r.content[:300]
    s = ImpersonationSession.objects.get(admin_user_id=admin.id)
    return admin, vol, c, s


def _ended_events(s: ImpersonationSession) -> int:
    return OutboxEvent.objects.filter(
        event_type="ImpersonationEnded", payload__session_id=str(s.id)
    ).count()


# ---------------------------------------------------------------------------------------
# N1: impersonation always ends before a session dies, from every path
# ---------------------------------------------------------------------------------------
def test_session_lifetime_expiry_ends_impersonation():
    admin, vol, c, s = _imp_setup("n1a@example.org")
    tick(9 * 3600)  # past the 8h MFA-role idle lifetime and 15m impersonation idle
    c.get(reverse("web:home"))
    s.refresh_from_db()
    assert s.ended_at is not None
    assert s.end_reason == ImpersonationSession.END_REASON_SESSION_EXPIRED
    assert _ended_events(s) == 1


def test_sign_in_cancel_while_impersonating_ends_it_and_audits_sign_out():
    admin, vol, c, s = _imp_setup("n1b@example.org")
    c.post(reverse("web:sign_in_cancel"))
    assert "_auth_user_id" not in c.session
    s.refresh_from_db()
    assert s.ended_at is not None
    assert _ended_events(s) == 1
    assert AuditEvent.objects.filter(action="auth.sign_out", actor_user_id=admin.id).exists()


def test_epoch_logout_ends_impersonation():
    admin, vol, c, s = _imp_setup("n1c@example.org")
    mfa.sign_out_everywhere(admin)
    c.get(reverse("web:home"))
    s.refresh_from_db()
    assert s.ended_at is not None
    assert s.end_reason == ImpersonationSession.END_REASON_SESSION_EXPIRED
    assert _ended_events(s) == 1


def test_sign_out_still_ends_impersonation():
    admin, vol, c, s = _imp_setup("n1d@example.org")
    c.post(reverse("web:sign_out"))
    s.refresh_from_db()
    assert s.ended_at is not None
    assert _ended_events(s) == 1


def test_periodic_sweep_ends_stale_idle_sessions():
    from ham.rules import RULES

    admin, vol, c, s = _imp_setup("n1e@example.org")
    # Simulate "nobody's browser ever comes back": push last_activity_at into the past
    # directly, bypassing any per-request check.
    s.last_activity_at = (
        clock_now() - RULES.auth.IMPERSONATION_IDLE_TIMEOUT - dt.timedelta(minutes=1)
    )
    s.save(update_fields=["last_activity_at"])
    ended = sweep_idle_impersonation_sessions(0)
    assert ended == 1
    s.refresh_from_db()
    assert s.ended_at is not None
    assert s.end_reason == ImpersonationSession.END_REASON_IDLE_TIMEOUT
    assert _ended_events(s) == 1


# ---------------------------------------------------------------------------------------
# N2: a fine-grained authz.denied survives an outer atomic (through the real view)
# ---------------------------------------------------------------------------------------
def test_authz_denied_recorded_through_the_view_despite_outer_atomic():
    director = _user("n2-director@example.org", roles.HAM_DIRECTOR)
    dsecret = _enroll(director)
    target = _user("n2-target@example.org", roles.VOLUNTEER)
    c = Client()
    _full_sign_in(c, director, dsecret)
    _step_up(c, dsecret, "role_change")
    r = c.post(
        reverse("web:admin_user_roles_confirm", args=[target.id]),
        {"add": [roles.ADMINISTRATOR], "reason": "x"},
    )
    assert r.status_code == 302
    assert not RoleAssignment.objects.filter(user=target, role=roles.ADMINISTRATOR).exists()
    assert AuditEvent.objects.filter(action="authz.denied", target_id="role.grant_global").exists()


# ---------------------------------------------------------------------------------------
# N3: Q-093 replace flow keeps the session alive long enough to show new recovery codes
# ---------------------------------------------------------------------------------------
def test_mfa_replace_keeps_session_and_shows_new_codes():
    u, secret = _admin("n3@example.org")
    c = Client()
    _full_sign_in(c, u, secret)
    r = c.get(reverse("web:mfa_setup") + "?replace=1")
    assert r.status_code == 302 and "step-up" in r["Location"]
    _step_up(c, secret, "mfa_replace")
    r = c.get(reverse("web:mfa_setup") + "?replace=1")
    assert r.status_code == 200
    new_secret = c.session["ham_totp_enroll_secret"]
    tick()
    r = c.post(reverse("web:mfa_setup"), {"step": "connect", "code": totp.current_code(new_secret)})
    assert r["Location"] == reverse("web:mfa_setup_codes")
    r = c.get(reverse("web:mfa_setup_codes"))
    assert r.status_code == 200
    assert "_auth_user_id" in c.session


# ---------------------------------------------------------------------------------------
# N6/M7 (Q-072): one step-up attempt budget per session, unknown kinds refused
# ---------------------------------------------------------------------------------------
def test_step_up_rejects_unknown_kind():
    u, secret = _admin("n6a@example.org")
    c = Client()
    _full_sign_in(c, u, secret)
    tick()
    r = c.post(reverse("web:step_up") + "?kind=made_up_kind", {"code": totp.current_code(secret)})
    assert r.status_code == 302
    assert not c.session.get("ham_step_up_at")


def test_step_up_attempt_budget_is_one_counter_for_the_whole_session():
    u, secret = _admin("n6b@example.org")
    c = Client()
    _full_sign_in(c, u, secret)
    # 5 wrong guesses under one kind bring the *session's* counter to the max; a 6th attempt
    # under a *different* kind must still trip the lockout immediately, because the budget is
    # one counter per session, not one per kind (the old per-kind dict would have given this
    # new kind its own fresh 5-guess budget).
    for _ in range(5):
        r = c.post(reverse("web:step_up") + "?kind=role_change", {"code": "000000"})
        assert r.status_code == 200
    r = c.post(reverse("web:step_up") + "?kind=audit_export", {"code": "000000"})
    assert r.status_code == 302
    assert r["Location"] == reverse("web:sign_in")
    assert AuditEvent.objects.filter(action="auth.step_up.locked").count() == 1
    assert "_auth_user_id" not in c.session


def test_step_up_lockout_signs_the_whole_session_out():
    # Security review round 3, N6: too many step-up guesses ends the whole session (the
    # step_up view itself refuses to run at all while impersonating -- security review L2 --
    # so `_end_session_fully`'s "also end any active impersonation" half is exercised
    # end-to-end by the N1 tests above; this checks the sign-out/audit half directly).
    u, secret = _admin("n6c@example.org")
    c = Client()
    _full_sign_in(c, u, secret)
    for _ in range(6):
        c.post(reverse("web:step_up") + "?kind=mfa_reset", {"code": "000000"})
    assert "_auth_user_id" not in c.session
    assert AuditEvent.objects.filter(action="auth.sign_out", actor_user_id=u.id).exists()


# ---------------------------------------------------------------------------------------
# N7: audit-export step-up stash expires and Cancel clears it
# ---------------------------------------------------------------------------------------
def test_audit_export_stash_expires_after_step_up_window():
    u, secret = _admin("n7a@example.org")
    c = Client()
    _full_sign_in(c, u, secret)
    r = c.post(reverse("web:audit_export"), {})
    assert r.status_code == 302
    tick(3 * 3600)  # abandon step-up; hours later, come back
    _step_up(c, secret, "audit_export")
    r = c.get(reverse("web:audit_export_download"))
    assert r.status_code == 302
    assert r["Location"] == reverse("web:audit_log")


def test_audit_export_stash_replays_when_fresh():
    u, secret = _admin("n7b@example.org")
    c = Client()
    _full_sign_in(c, u, secret)
    r = c.post(reverse("web:audit_export"), {})
    assert r.status_code == 302
    _step_up(c, secret, "audit_export")
    r = c.get(reverse("web:audit_export_download"))
    assert r.status_code == 200 and r["Content-Type"].startswith("text/csv")


def test_step_up_cancel_clears_the_audit_export_stash():
    u, secret = _admin("n7c@example.org")
    c = Client()
    _full_sign_in(c, u, secret)
    r = c.post(reverse("web:audit_export"), {})
    assert r.status_code == 302
    step_up_url = r["Location"]  # carries the real `?cancel=` `redirect_to_step_up` built
    assert "ham_audit_export_stash" in c.session
    r = c.post(step_up_url, {"cancel": "1"})
    assert r.status_code == 302
    assert "ham_audit_export_stash" not in c.session


# ---------------------------------------------------------------------------------------
# N8: never fall back to an email address as a display name
# ---------------------------------------------------------------------------------------
def test_api_me_never_falls_back_to_email():
    vol = _user("n8@example.org", roles.VOLUNTEER)
    SharedIdentityProfile.objects.get_or_create(user=vol)
    c = Client()
    c.force_login(vol)
    session = c.session
    session["ham_session_epoch"] = vol.session_epoch
    session.save()
    data = c.get("/api/v1/me").json()
    assert "n8@example.org" not in json.dumps(data)
    assert data["display_name"].startswith("Member ")


def test_impersonation_banner_never_falls_back_to_email():
    admin, vol, c, s = _imp_setup("n8b@example.org")
    r = c.get(reverse("web:home"))
    assert b"t-n8b@example.org" not in r.content


def test_display_names_for_never_falls_back_to_email():
    from ham.identity.services import display_names_for

    vol = _user("n8c@example.org", roles.VOLUNTEER)
    SharedIdentityProfile.objects.get_or_create(user=vol)
    names = display_names_for([vol.id])
    assert names[vol.id] == f"Member {str(vol.id)[:8]}"


# ---------------------------------------------------------------------------------------
# N5: the sign-in IP throttle only trusts configured proxy hops
# ---------------------------------------------------------------------------------------
def test_client_ip_ignores_spoofed_xff_by_default(settings):
    from ham.web.auth_views import _client_ip

    settings.HAM_TRUSTED_PROXY_COUNT = 0
    rf = RequestFactory()
    request = rf.post("/sign-in", HTTP_X_FORWARDED_FOR="10.0.0.1, 1.2.3.4")
    request.META["REMOTE_ADDR"] = "9.9.9.9"
    assert _client_ip(request) == "9.9.9.9"


def test_client_ip_trusts_exactly_the_configured_hop_count(settings):
    from ham.web.auth_views import _client_ip

    settings.HAM_TRUSTED_PROXY_COUNT = 1
    rf = RequestFactory()
    request = rf.post("/sign-in", HTTP_X_FORWARDED_FOR="10.0.0.1, 1.2.3.4")
    request.META["REMOTE_ADDR"] = "9.9.9.9"
    # Only Render's own edge hop (the right-most one) is trusted; the left-most is
    # client-controlled and must not be used.
    assert _client_ip(request) == "1.2.3.4"


# ---------------------------------------------------------------------------------------
# N9: encrypted job payloads are time-bounded
# ---------------------------------------------------------------------------------------
def test_job_payload_decrypt_rejects_an_expired_token():
    import time

    from cryptography.fernet import InvalidToken

    from ham.platform.crypto import decrypt, encrypt

    # Fernet's own TTL check is against the real wall clock (its token embeds a real
    # creation timestamp), not `ham.platform.clock` -- so this needs a real, short sleep
    # rather than `tick()`.
    token = encrypt("hello")
    time.sleep(2.1)
    with pytest.raises(InvalidToken):
        decrypt(token, ttl_seconds=1)
    # sanity: no ttl (or a generous one) still works
    assert decrypt(token) == "hello"
    assert decrypt(token, ttl_seconds=3600) == "hello"


# ---------------------------------------------------------------------------------------
# L5: one-time recovery codes are cleared from the session right after display
# ---------------------------------------------------------------------------------------
def test_recovery_codes_cleared_from_session_after_one_render():
    u = _user("l5@example.org", roles.ADMINISTRATOR)  # not yet enrolled
    c = Client()
    r = _email_step(c, u.email)
    assert r.status_code == 302 and r["Location"] == reverse("web:mfa_setup")
    c.get(reverse("web:mfa_setup"))
    secret = c.session["ham_totp_enroll_secret"]
    r = c.post(reverse("web:mfa_setup"), {"step": "connect", "code": totp.current_code(secret)})
    assert r.status_code == 302 and r["Location"] == reverse("web:mfa_setup_codes")
    assert c.session.get("ham_recovery_codes_once")

    r = c.get(reverse("web:mfa_setup_codes"))
    assert r.status_code == 200
    # The plaintext codes must be gone from the session after this one render, even though
    # "Finish" was never pressed.
    assert not c.session.get("ham_recovery_codes_once")

    # A second GET (e.g. a refresh) must not show the codes again, but must still let the
    # page's own POST complete.
    r = c.get(reverse("web:mfa_setup_codes"))
    assert r.status_code == 200
    assert (
        b"You&#x27;ve already viewed these codes" in r.content
        or b"already viewed these codes" in r.content
    )

    r = c.post(reverse("web:mfa_setup_codes"))
    assert r.status_code == 302


# ---------------------------------------------------------------------------------------
# Q-096: an invitation carrying a non-Volunteer role notifies every active Administrator
# ---------------------------------------------------------------------------------------
def test_invitation_with_leadership_role_notifies_administrators():
    from ham.identity.notifications import _build_invite_admin_notices
    from ham.outbox.models import OutboxEvent

    admin, _secret = _admin("q096-admin@example.org")
    invited = User.objects.create_user(email="q096-invitee@example.org")
    SharedIdentityProfile.objects.create(user=invited, full_name="Pat Invitee")
    event = OutboxEvent(
        event_type="UserCreated",
        aggregate_type="user",
        aggregate_id=invited.id,
        payload={"roles": [roles.HAM_DIRECTOR], "invited_by": str(admin.id)},
        schema_version=1,
    )
    emails = _build_invite_admin_notices(event, user=invited, inviter_name="A HAM leader")
    assert len(emails) == 1
    assert emails[0].to == admin.email


def test_invitation_volunteer_only_does_not_notify_administrators():
    from ham.identity.notifications import _build_invite_admin_notices
    from ham.outbox.models import OutboxEvent

    invited = User.objects.create_user(email="q096b-invitee@example.org")
    event = OutboxEvent(
        event_type="UserCreated",
        aggregate_type="user",
        aggregate_id=invited.id,
        payload={"roles": [roles.VOLUNTEER], "invited_by": "x"},
        schema_version=1,
    )
    emails = _build_invite_admin_notices(event, user=invited, inviter_name="A HAM leader")
    assert emails == []


# ---------------------------------------------------------------------------------------
# Q-098: only someone who could have sent an invitation may resend/cancel it
# ---------------------------------------------------------------------------------------
def test_assistant_director_cannot_cancel_a_director_sent_leadership_invitation():
    from ham.authz.commands import PermissionDenied
    from ham.authz.context import ActorContext
    from ham.identity.services import cancel_invitation

    invited = User.objects.create_user(email="q098-invited@example.org")
    RoleAssignment.objects.create(user=invited, role=roles.HAM_DIRECTOR, granted_at=clock_now())
    ad = _user("q098-ad@example.org", roles.ASSISTANT_DIRECTOR)
    ctx = ActorContext(
        user_id=ad.id,
        real_user_id=None,
        roles=frozenset({roles.ASSISTANT_DIRECTOR}),
        scoped_roles=(),
        is_active=True,
        mfa_satisfied=True,
        impersonation_id=None,
    )
    with pytest.raises(PermissionDenied):
        cancel_invitation(ctx, user_id=invited.id, reason="")


def test_assistant_director_can_cancel_a_volunteer_only_invitation():
    from ham.authz.context import ActorContext
    from ham.identity.services import cancel_invitation

    invited = User.objects.create_user(email="q098b-invited@example.org")
    RoleAssignment.objects.create(user=invited, role=roles.VOLUNTEER, granted_at=clock_now())
    ad = _user("q098b-ad@example.org", roles.ASSISTANT_DIRECTOR)
    ctx = ActorContext(
        user_id=ad.id,
        real_user_id=None,
        roles=frozenset({roles.ASSISTANT_DIRECTOR}),
        scoped_roles=(),
        is_active=True,
        mfa_satisfied=True,
        impersonation_id=None,
    )
    cancel_invitation(ctx, user_id=invited.id, reason="")
    invited.refresh_from_db()
    assert invited.is_disabled
