"""FIX-E N3/L8/M4 regression: `_after_verified`'s link-regeneration branch must require
`challenge.request_id == session request id`, never trust the session value alone, and the
resulting `regenerate_link_for_own_request` command must leave a record of what verified it
(method + challenge id, on the audit event and as a `RequestContactVerification(purpose=
"link_regeneration")` row). New file per wave brief.
"""

from __future__ import annotations

import uuid

import pytest
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.urls import reverse

from ham.authz.context import RequesterContext, SystemContext
from ham.platform import otp
from ham.platform.clock import now as clock_now
from ham.requester_portal import services as portal_services
from ham.requester_portal.models import RequesterVerificationChallenge
from ham.requests.models import RequestContactVerification
from ham.requests.services import complete_intake_checks, submit_request
from ham.rules import RULES
from tests.requests.conftest import make_payload

pytestmark = pytest.mark.django_db


def _requester_ctx():
    return RequesterContext(request_id=None)


def _submitted_request(email: str):
    req = submit_request(
        _requester_ctx(),
        draft_id=uuid.uuid4(),
        verification_id=uuid.uuid4(),
        payload=make_payload(email=email, verified_value=email),
    )
    complete_intake_checks(SystemContext(), request_id=req.id)
    return req


def test_after_verified_refuses_when_challenge_request_id_does_not_match_session(
    client, real_portal_lookups
):
    """A tampered/stale session value for `ham_intake_link_regen_request_id` (pointing at
    request B) must not let a code sent for request A's challenge regenerate a link for B --
    the challenge's own `request_id` is the only thing trusted. With the N3 fix,
    `verify_code` itself already refuses (it selects the challenge by the *passed*
    `request_id`, i.e. request B's, and finds nothing there); `_after_verified`'s own
    `challenge.request_id == session request id` check (L8) is defense in depth for the same
    class of bug one layer further in."""
    request_a = _submitted_request("victim@example.org")
    request_b = _submitted_request("other@example.org")

    code_result = portal_services.request_link_regeneration_code(
        request_id=request_a.id, email="victim@example.org"
    )
    assert code_result.status == "sent"
    challenge = RequesterVerificationChallenge.objects.get(id=code_result.challenge_id)
    challenge.code_hash = otp.hash_value("123456")
    challenge.save(update_fields=["code_hash"])
    assert challenge.request_id == request_a.id

    session = client.session
    session["ham_intake_verify"] = {
        "purpose": RequesterVerificationChallenge.PURPOSE_LINK_REGENERATION,
        "email": "victim@example.org",
    }
    # Tampered: the session claims request B, but the code was sent for request A.
    session["ham_intake_link_regen_request_id"] = str(request_b.id)
    session.save()

    resp = client.post(reverse("web:request_help_verify"), {"code": "123456"})
    assert resp.status_code == 422  # verify_code: no_challenge for request B's id

    # Nothing was issued/regenerated for either request as a result of this attempt.
    assert not RequestContactVerification.objects.filter(
        request_id=request_b.id, purpose="link_regeneration"
    ).exists()
    assert not RequestContactVerification.objects.filter(
        request_id=request_a.id, purpose="link_regeneration"
    ).exists()


def test_after_verified_itself_refuses_a_mismatched_challenge(real_portal_lookups):
    """Direct unit test of `_after_verified`'s own `challenge.request_id == session request
    id` check (L8 defense in depth), bypassing `verify_code`'s own request_id-scoped
    selection entirely -- a hand-built challenge object stands in for "some other code path
    that got a challenge for the wrong request past `verify_code`"."""
    from ham.web.views_requester import _after_verified

    request_a = _submitted_request("victim3@example.org")
    request_b = _submitted_request("other3@example.org")

    now = clock_now()
    challenge = RequesterVerificationChallenge.objects.create(
        purpose=RequesterVerificationChallenge.PURPOSE_LINK_REGENERATION,
        request_id=request_a.id,  # the challenge really belongs to request A ...
        email_key=otp.hash_value("victim3@example.org"),
        code_hash=otp.hash_value("111111"),
        link_token_hash=otp.hash_value("some-token"),
        created_at=now,
        expires_at=now + RULES.intake.REQUESTER_CODE_LIFETIME,
    )

    factory = RequestFactory()
    django_request = factory.post("/request-help/verify")
    SessionMiddleware(lambda r: None).process_request(django_request)
    django_request.session["ham_intake_verify"] = {
        "purpose": RequesterVerificationChallenge.PURPOSE_LINK_REGENERATION,
        "email": "victim3@example.org",
    }
    # ... but the session (somehow) claims request B.
    django_request.session["ham_intake_link_regen_request_id"] = str(request_b.id)
    django_request.session.save()

    resp = _after_verified(
        django_request,
        purpose=RequesterVerificationChallenge.PURPOSE_LINK_REGENERATION,
        challenge=challenge,
    )
    assert resp.status_code == 302
    assert resp.url == reverse("web:request_help_start")
    assert not RequestContactVerification.objects.filter(
        request_id__in=(request_a.id, request_b.id), purpose="link_regeneration"
    ).exists()


def test_after_verified_regenerates_and_records_verification_when_ids_match(
    client, real_portal_lookups
):
    request_a = _submitted_request("victim2@example.org")

    code_result = portal_services.request_link_regeneration_code(
        request_id=request_a.id, email="victim2@example.org"
    )
    challenge = RequesterVerificationChallenge.objects.get(id=code_result.challenge_id)
    challenge.code_hash = otp.hash_value("654321")
    challenge.save(update_fields=["code_hash"])

    session = client.session
    session["ham_intake_verify"] = {
        "purpose": RequesterVerificationChallenge.PURPOSE_LINK_REGENERATION,
        "email": "victim2@example.org",
    }
    session["ham_intake_link_regen_request_id"] = str(request_a.id)
    session.save()

    resp = client.post(reverse("web:request_help_verify"), {"code": "654321"})
    assert resp.status_code == 302
    assert resp.url != reverse("web:request_help_start")

    # L8/M4: an append-only verification row for this regeneration, distinguishable from an
    # intake verification by purpose.
    row = RequestContactVerification.objects.get(
        request_id=request_a.id, purpose="link_regeneration"
    )
    assert row.method == "email_code"
    assert row.challenge_id == challenge.id
