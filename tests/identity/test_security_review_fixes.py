"""Regression tests for the step-1 privacy/security review
(`/tmp/.../scratchpad/reviews/security.md`, PRD-guardian review, UX review C1/C4/M1-M4/M8),
adapted from the reviewer's own probe tests (`scratchpad/test_sec_probe.py`).
"""

from __future__ import annotations

import datetime as dt
import re

import pytest
from django.core import mail
from django.test import Client
from django.urls import reverse

from ham import jobs
from ham.authz import roles
from ham.identity import mfa, totp
from ham.identity.models import RoleAssignment, User
from ham.platform.clock import now as clock_now

pytestmark = pytest.mark.django_db


def _admin(email: str) -> tuple[User, str]:
    u = User.objects.create_user(email=email)
    RoleAssignment.objects.create(user=u, role=roles.ADMINISTRATOR, granted_at=clock_now())
    e = mfa.start_enrollment(u)
    mfa.confirm_enrollment(u, secret=e.secret, code=totp.current_code(e.secret))
    return u, e.secret


def _email_step(client: Client, email: str):
    client.post(reverse("web:sign_in"), {"email": email})
    jobs.run_due_jobs_now()
    body = str(mail.outbox[-1].body)
    match = re.search(r"code is (\d{3}) (\d{3})", body)
    assert match is not None
    code = match.group(1) + match.group(2)
    return client.post(reverse("web:sign_in_code"), {"code": code})


# ---------------------------------------------------------------------------------------
# C1 / PRD B1: MFA bypass via re-enrollment
# ---------------------------------------------------------------------------------------
def test_mfa_bypass_via_reenrollment_is_blocked():
    user, original_secret = _admin("victim-admin@example.org")
    c = Client()
    r = _email_step(c, user.email)
    assert r.status_code == 302 and r["Location"] == reverse("web:sign_in_mfa")

    # An attacker who only has the emailed code must never reach enrollment for an
    # already-enrolled account.
    r = c.get(reverse("web:mfa_setup"))
    assert r.status_code == 302
    assert r["Location"] == reverse("web:sign_in_mfa")

    r = c.post(reverse("web:mfa_setup"), {"step": "connect", "code": "000000"})
    assert r.status_code == 302

    # The account still isn't signed in, and the original authenticator still works.
    r = c.get(reverse("web:admin_users"))
    assert r.status_code in (302, 404)
    assert mfa.verify_totp(user, totp.current_code(original_secret))


def test_confirm_enrollment_refuses_to_overwrite_without_replace_flag(make_user):
    user = make_user("victim2@example.org")
    RoleAssignment.objects.create(user=user, role=roles.ADMINISTRATOR, granted_at=clock_now())
    e = mfa.start_enrollment(user)
    mfa.confirm_enrollment(user, secret=e.secret, code=totp.current_code(e.secret))

    e2 = mfa.start_enrollment(user)
    with pytest.raises(ValueError):
        mfa.confirm_enrollment(user, secret=e2.secret, code=totp.current_code(e2.secret))

    # replace=True (only ever reachable, per ham.web.auth_views.mfa_setup, once fully signed
    # in with MFA this session + a fresh step-up) does overwrite, and audits/emails it.
    mail.outbox = []
    mfa.confirm_enrollment(user, secret=e2.secret, code=totp.current_code(e2.secret), replace=True)
    assert mfa.verify_totp(user, totp.current_code(e2.secret))
    jobs.run_due_jobs_now()
    assert len(mail.outbox) == 1
    assert "authenticator was changed" in mail.outbox[0].subject


# ---------------------------------------------------------------------------------------
# H2: TOTP replay protection
# ---------------------------------------------------------------------------------------
def test_totp_replay_is_rejected(make_user):
    user = make_user("replay@example.org")
    RoleAssignment.objects.create(user=user, role=roles.ADMINISTRATOR, granted_at=clock_now())
    e = mfa.start_enrollment(user)
    mfa.confirm_enrollment(user, secret=e.secret, code=totp.current_code(e.secret))

    code = totp.current_code(e.secret)
    assert mfa.verify_totp(user, code)
    assert not mfa.verify_totp(user, code)  # the same code must not work twice


# ---------------------------------------------------------------------------------------
# H1 / Q-072: step-up attempt limit
# ---------------------------------------------------------------------------------------
def test_step_up_has_an_attempt_limit_and_is_audited(client: Client, make_user):
    from ham.audit.models import AuditEvent

    admin = make_user("adm3@example.org")
    RoleAssignment.objects.create(user=admin, role=roles.ADMINISTRATOR, granted_at=clock_now())
    e = mfa.start_enrollment(admin)
    mfa.confirm_enrollment(admin, secret=e.secret, code=totp.current_code(e.secret))
    client.force_login(admin)
    session = client.session
    session["ham_mfa_satisfied"] = True
    session.save()

    from ham.rules import RULES

    responses = []
    for i in range(RULES.auth.MFA_CODE_MAX_ATTEMPTS + 3):
        r = client.post(reverse("web:step_up") + "?kind=audit_export", {"code": f"{i:06d}"})
        responses.append(r.status_code)

    # After the limit, the view stops rendering the form again (redirects the person away)
    # rather than accepting unlimited guesses.
    assert responses.count(200) <= RULES.auth.MFA_CODE_MAX_ATTEMPTS
    assert AuditEvent.objects.filter(action="auth.step_up.locked").exists()


def test_step_up_refuses_while_impersonating(client: Client, make_user):
    from ham.identity.models import ImpersonationSession

    admin = make_user("adm4@example.org")
    RoleAssignment.objects.create(user=admin, role=roles.ADMINISTRATOR, granted_at=clock_now())
    e = mfa.start_enrollment(admin)
    mfa.confirm_enrollment(admin, secret=e.secret, code=totp.current_code(e.secret))
    target = make_user("vol4@example.org")
    RoleAssignment.objects.create(user=target, role=roles.VOLUNTEER, granted_at=clock_now())

    session_row = ImpersonationSession.objects.create(
        admin_user_id=admin.id,
        target_user_id=target.id,
        reason="checking something",
        started_at=clock_now(),
        last_activity_at=clock_now(),
    )
    client.force_login(admin)
    session = client.session
    session["ham_impersonation_id"] = str(session_row.id)
    session["ham_mfa_satisfied"] = True
    session.save()

    r = client.get(reverse("web:step_up") + "?kind=audit_export")
    assert r.status_code == 302
    assert r["Location"] == reverse("web:home")


# ---------------------------------------------------------------------------------------
# M2: race-safe sign-in code verification (select_for_update) — smoke test that it still
# accepts a correct code and rejects a stale one; the real race is exercised structurally
# (both paths now run inside one atomic, locked block).
# ---------------------------------------------------------------------------------------
def test_sign_in_code_verification_is_still_correct_after_locking(client: Client, make_user):
    user = make_user("kevin@example.org")
    client.post(reverse("web:sign_in"), {"email": user.email})
    jobs.run_due_jobs_now()
    body = str(mail.outbox[-1].body)
    match = re.search(r"code is (\d{3}) (\d{3})", body)
    assert match is not None
    code = match.group(1) + match.group(2)

    from ham.identity import authn

    assert not authn.verify_code(email=user.email, code="000000").ok
    result = authn.verify_code(email=user.email, code=code)
    assert result.ok


# ---------------------------------------------------------------------------------------
# M3: per-IP throttle and daily failed-attempt cap
# ---------------------------------------------------------------------------------------
def test_sign_in_request_throttles_by_ip(make_user):
    from ham.identity import authn
    from ham.rules import RULES

    limit = RULES.auth.SIGN_IN_REQUESTS_PER_IP_PER_HOUR
    for i in range(limit):
        result = authn.request_sign_in(email=f"person{i}@example.org", ip_address="1.2.3.4")
        assert result.status == "sent"
    result = authn.request_sign_in(email="one-more@example.org", ip_address="1.2.3.4")
    assert result.status == "rate_limited"


def test_sign_in_code_daily_failed_attempt_cap(make_user):
    from ham.identity import authn
    from ham.rules import RULES

    user = make_user("locked-out@example.org")
    cap = RULES.auth.SIGN_IN_FAILED_ATTEMPTS_PER_ADDRESS_PER_DAY
    # Burn through the cap across several fresh challenges (each challenge's own
    # per-challenge limit is smaller, so this spans a few of them).
    attempted = 0
    while attempted < cap:
        authn.request_sign_in(email=user.email)
        for _ in range(min(RULES.auth.SIGN_IN_CODE_MAX_ATTEMPTS, cap - attempted)):
            authn.verify_code(email=user.email, code="000000")
            attempted += 1
    authn.request_sign_in(email=user.email)
    result = authn.verify_code(email=user.email, code="000000")
    assert result.reason == "locked"


# ---------------------------------------------------------------------------------------
# H3 / UX M8: MFA reset and "sign out everywhere" invalidate other sessions
# ---------------------------------------------------------------------------------------
def test_mfa_reset_invalidates_other_sessions_via_epoch(client: Client, make_user):
    from ham.authz.context import ActorContext

    admin = make_user("nadia9@example.org")
    RoleAssignment.objects.create(user=admin, role=roles.ADMINISTRATOR, granted_at=clock_now())
    e = mfa.start_enrollment(admin)
    mfa.confirm_enrollment(admin, secret=e.secret, code=totp.current_code(e.secret))

    target = make_user("marcus9@example.org")
    RoleAssignment.objects.create(user=target, role=roles.HAM_DIRECTOR, granted_at=clock_now())
    e2 = mfa.start_enrollment(target)
    mfa.confirm_enrollment(target, secret=e2.secret, code=totp.current_code(e2.secret))

    client.force_login(target)
    session = client.session
    session["ham_mfa_satisfied"] = True
    session["ham_session_epoch"] = target.session_epoch
    session.save()
    assert client.get(reverse("web:audit_log")).status_code in (200, 302)  # not yet reset

    admin_ctx = ActorContext(
        user_id=admin.id,
        real_user_id=None,
        roles=frozenset({roles.ADMINISTRATOR}),
        is_active=True,
        mfa_satisfied=True,
        step_up_at={"mfa_reset": clock_now()},
    )
    mfa.reset_mfa(admin_ctx, user_id=target.id, verification_method="phone_call")

    # The same browser session (still holding the *old* epoch) must be signed out on its
    # very next request, not merely once its own idle timeout eventually fires.
    r = client.get(reverse("web:me"))
    assert r.status_code == 302
    assert r["Location"].startswith(reverse("web:sign_in"))


def test_sign_out_everywhere_invalidates_other_sessions(make_user):
    user = make_user("ruth9@example.org")
    RoleAssignment.objects.create(user=user, role=roles.PASTOR, granted_at=clock_now())
    e = mfa.start_enrollment(user)
    mfa.confirm_enrollment(user, secret=e.secret, code=totp.current_code(e.secret))

    other_browser = Client()
    other_browser.force_login(user)
    other_session = other_browser.session
    other_session["ham_mfa_satisfied"] = True
    other_session["ham_session_epoch"] = user.session_epoch
    other_session.save()

    this_browser = Client()
    this_browser.force_login(user)
    session = this_browser.session
    session["ham_mfa_satisfied"] = True
    session["ham_session_epoch"] = user.session_epoch
    session.save()

    r = this_browser.post(reverse("web:me_sign_out_everywhere"))
    assert r.status_code == 200

    r = other_browser.get(reverse("web:me"))
    assert r.status_code == 302
    assert r["Location"].startswith(reverse("web:sign_in"))


# ---------------------------------------------------------------------------------------
# M4: CSV formula injection
# ---------------------------------------------------------------------------------------
def test_csv_export_neutralizes_formula_injection():
    from ham.audit.export import build_csv
    from ham.audit.services import record

    event = record(
        ctx=None,
        actor_type="system",
        action="x",
        target_type="user",
        target_id="1",
        reason='=HYPERLINK("http://evil","x")',
    )
    out = build_csv([event]).decode()
    last_line = out.splitlines()[-1]
    assert "'=HYPERLINK" in last_line
    assert '"=HYPERLINK("http://evil"' not in last_line


# ---------------------------------------------------------------------------------------
# PRD B2: absolute sign-in link
# ---------------------------------------------------------------------------------------
def test_sign_in_link_email_contains_an_absolute_url(settings, make_user):
    from ham.identity import authn

    settings.HAM_BASE_URL = "https://ham.example.org"
    user = make_user("someone@example.org")
    authn.request_sign_in(email=user.email)
    jobs.run_due_jobs_now()
    body = str(mail.outbox[-1].body)
    assert "https://ham.example.org/sign-in/link/" in body


# ---------------------------------------------------------------------------------------
# L1: recovery codes and sign-in codes are HMAC'd, not a plain unsalted hash
# ---------------------------------------------------------------------------------------
def test_recovery_code_hash_is_not_plain_sha256(make_user):
    import hashlib

    user = make_user("hash-check@example.org")
    e = mfa.start_enrollment(user)
    codes = mfa.confirm_enrollment(user, secret=e.secret, code=totp.current_code(e.secret))
    from ham.identity.models import RecoveryCode

    stored_hashes = set(RecoveryCode.objects.filter(user=user).values_list("code_hash", flat=True))
    for code in codes:
        normalized = code.strip().lower().replace("-", "").replace(" ", "")
        plain_sha256 = hashlib.sha256(normalized.encode()).hexdigest()
        assert plain_sha256 not in stored_hashes


# ---------------------------------------------------------------------------------------
# L6: bootstrap_admin refuses a second Administrator without --force
# ---------------------------------------------------------------------------------------
def test_bootstrap_admin_refuses_when_an_admin_already_exists(make_user):
    from django.core.management import call_command
    from django.core.management.base import CommandError

    existing = make_user("first-admin@example.org")
    RoleAssignment.objects.create(user=existing, role=roles.ADMINISTRATOR, granted_at=clock_now())

    with pytest.raises(CommandError):
        call_command("bootstrap_admin", email="second-admin@example.org")

    call_command("bootstrap_admin", email="second-admin@example.org", force=True)
    assert User.objects.filter(email="second-admin@example.org").exists()


# ---------------------------------------------------------------------------------------
# M1 / PRD Major 6(a): idle-timeout impersonation rebuilds request.actor within the request
# ---------------------------------------------------------------------------------------
def test_idle_expired_impersonation_rebuilds_actor_same_request(client: Client, make_user):
    from ham.identity.models import ImpersonationSession

    admin = make_user("adm2@example.org")
    RoleAssignment.objects.create(user=admin, role=roles.ADMINISTRATOR, granted_at=clock_now())
    e = mfa.start_enrollment(admin)
    mfa.confirm_enrollment(admin, secret=e.secret, code=totp.current_code(e.secret))
    vol = make_user("vol2@example.org")
    RoleAssignment.objects.create(user=vol, role=roles.VOLUNTEER, granted_at=clock_now())

    s = ImpersonationSession.objects.create(
        admin_user_id=admin.id,
        target_user_id=vol.id,
        reason="x",
        started_at=clock_now() - dt.timedelta(hours=1),
        last_activity_at=clock_now() - dt.timedelta(minutes=20),
    )
    client.force_login(admin)
    session = client.session
    session["ham_impersonation_id"] = str(s.id)
    session["ham_mfa_satisfied"] = True
    session.save()

    r = client.get(reverse("web:home"))
    actor = r.wsgi_request.actor  # type: ignore[attr-defined]
    assert not actor.is_impersonating
    assert actor.user_id == admin.id

    s.refresh_from_db()
    assert s.ended_at is not None
    assert s.end_reason == ImpersonationSession.END_REASON_IDLE_TIMEOUT


# ---------------------------------------------------------------------------------------
# C2: no PII in logs or job args during a full sign-in
# ---------------------------------------------------------------------------------------
def test_sign_in_never_logs_email_code_or_token(client: Client, caplog, make_user):
    import logging

    caplog.set_level(logging.DEBUG)
    user = make_user("privacy@example.org")
    client.post(reverse("web:sign_in"), {"email": user.email})
    jobs.run_due_jobs_now()
    body = str(mail.outbox[-1].body)
    match = re.search(r"code is (\d{3}) (\d{3})", body)
    assert match is not None
    code = match.group(1) + match.group(2)
    client.post(reverse("web:sign_in_code"), {"code": code})

    for record in caplog.records:
        message = record.getMessage()
        assert user.email not in message
        assert code not in message
        assert user.email not in str(record.__dict__)
        assert code not in str(record.__dict__)

    from django.db import connection

    from ham.jobs import app as procrastinate_app  # noqa: F401

    with connection.cursor() as cursor:
        cursor.execute("SELECT args FROM procrastinate_jobs")
        rows = cursor.fetchall()
    for (args,) in rows:
        text = str(args)
        assert user.email not in text
        assert code not in text
