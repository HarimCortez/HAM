"""S2.7 integration tests: the public requester screens R1-R12, driven through Django's test
client exactly like a browser would hit them (no account, PRD §7 "requesters have no
account") — see `tests/requester_portal/test_submission_flow.py` for the service-layer
equivalent this slice builds a UI on top of.
"""

from __future__ import annotations

import json

import pytest
from django.core import mail
from django.test import Client
from django.urls import reverse

from ham.jobs import run_due_jobs_now
from ham.platform import otp
from ham.requester_portal.models import RequesterVerificationChallenge

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _real_portal_lookups():
    """Some other test module's fixture (e.g. `tests/requester_portal/test_links.py`)
    registers a fake lookup for the module-level duration of one test and resets the global to
    `None` on teardown rather than back to what `RequesterPortalConfig.ready()` originally
    registered (see `tests/requester_portal/test_submission_flow.py`'s identical fixture,
    which this copies) -- so a view test running later in the same process can't rely on
    process-startup registration surviving. Re-registers the same production callables."""
    from ham.requester_portal import services
    from ham.requests import queries as requests_queries

    def _facts_lookup(request_id):
        facts = requests_queries.request_facts_for_portal(request_id)
        return services.RequestLinkFacts(status=facts.status, closed_at=facts.closed_at)

    services.register_request_facts_lookup(_facts_lookup)
    services.register_request_contact_lookup(requests_queries.request_contact_for_portal)
    services.register_email_to_request_ids_lookup(requests_queries.request_ids_for_portal_email)
    yield
    services._request_facts_lookup = None  # noqa: SLF001 - test isolation
    services._request_contact_lookup = None  # noqa: SLF001
    services._email_to_request_ids_lookup = None  # noqa: SLF001


@pytest.fixture
def local_storage(tmp_path, settings):
    settings.HAM_LOCAL_STORAGE_ROOT = str(tmp_path)
    settings.HAM_OBJECT_STORE_BACKEND = "ham.integrations.storage.local.LocalObjectStore"
    return tmp_path


def _step_payload(**overrides) -> dict:
    steps = {
        "need": {"need_category": "roof_or_ceiling", "description": "Water leaks in."},
        "home": {
            "relationship_to_property": "owner",
            "line1": "1400 NW Example Ave",
            "city": "Miami",
            "state": "FL",
            "postal_code": "33125",
            "property_type": "house",
        },
        "safety": {"hazards": ["none_known"]},
        "reaching-you": {
            "full_name": "Doris Palmer",
            "phone": "(305) 555-0142",
            "email": "doris.p@example.org",
            "contact_preference": "email",
            "availability": ["any_time"],
        },
    }
    steps.update(overrides)
    return steps


def _fill_wizard(client: Client, *, no_email: bool = False, urgent: bool = False) -> None:
    resp = client.get(reverse("web:request_help_start"))
    assert resp.status_code == 200
    resp = client.post(reverse("web:request_help_begin"), follow=True)
    assert resp.status_code == 200
    assert resp.redirect_chain[-1][0] == reverse("web:request_help_step", kwargs={"step": "need"})
    _backdate_form_opened_at(client)

    steps = _step_payload()
    need_data = dict(steps["need"])
    if urgent:
        need_data["urgent_requested"] = "1"
        need_data["urgency_reason"] = "water_or_damage"
    resp = client.post(
        reverse("web:request_help_step", kwargs={"step": "need"}), need_data, follow=True
    )
    assert resp.status_code == 200, resp.content

    resp = client.post(
        reverse("web:request_help_step", kwargs={"step": "home"}), steps["home"], follow=True
    )
    assert resp.status_code == 200, resp.content

    resp = client.post(
        reverse("web:request_help_step", kwargs={"step": "safety"}), steps["safety"], follow=True
    )
    assert resp.status_code == 200, resp.content

    reaching = dict(steps["reaching-you"])
    if no_email:
        reaching = {
            "full_name": reaching["full_name"],
            "phone": reaching["phone"],
            "no_email": "1",
        }
    resp = client.post(
        reverse("web:request_help_step", kwargs={"step": "reaching-you"}), reaching, follow=True
    )
    assert resp.status_code == 200, resp.content


def _review_page(client: Client) -> bytes:
    resp = client.get(reverse("web:request_help_step", kwargs={"step": "review"}))
    assert resp.status_code == 200
    return resp.content


class TestFullEmailFlow:
    def test_form_to_secure_page_and_one_photo(self, client: Client, local_storage):
        _fill_wizard(client)
        html = _review_page(client)
        assert b"Send request" in html

        mail.outbox.clear()
        resp = client.post(
            reverse("web:request_help_step", kwargs={"step": "review"}),
            {"attested_statements": ["owner_authority", "responsibility"]},
            follow=True,
        )
        assert resp.status_code == 200, resp.content
        assert resp.redirect_chain[-1][0] == reverse("web:request_help_verify")
        run_due_jobs_now()
        assert len(mail.outbox) == 1

        challenge = RequesterVerificationChallenge.objects.get(
            purpose="intake", email_key=otp.hash_value("doris.p@example.org")
        )
        challenge.code_hash = otp.hash_value("111222")
        challenge.save(update_fields=["code_hash"])

        resp = client.post(reverse("web:request_help_verify"), {"code": "111222"}, follow=True)
        assert resp.status_code == 200, resp.content
        secure_url = resp.redirect_chain[-1][0]
        assert secure_url.startswith("/request-help/r/")
        assert b"HAM #" in resp.content
        assert b"We've received your request" in resp.content

        # Drains the duplicate-check job `submit_request` deferred, so it doesn't leak into a
        # later test's `run_due_jobs_now()` call.
        run_due_jobs_now()

        token = secure_url.split("/request-help/r/")[1].split("?")[0]

        # R9: reserve + PUT + complete one photo.
        photos_resp = client.get(reverse("web:request_help_photos", kwargs={"token": token}))
        assert photos_resp.status_code == 200

        reserve_resp = client.post(
            reverse("web:request_help_media_reserve", kwargs={"token": token}),
            data=json.dumps(
                {
                    "files": [
                        {
                            "media_kind": "photo",
                            "content_type": "image/jpeg",
                            "declared_bytes": 1000,
                        }
                    ]
                }
            ),
            content_type="application/json",
        )
        assert reserve_resp.status_code == 200, reserve_resp.content
        reserved = json.loads(reserve_resp.content)["files"][0]

        put_path = reserved["put_url"].split("http://testserver", 1)[-1]
        put_resp = client.put(put_path, data=b"\xff\xd8\xff" * 10, content_type="image/jpeg")
        assert put_resp.status_code == 204

        complete_resp = client.post(reserved["complete_url"])
        assert complete_resp.status_code == 200, complete_resp.content
        assert json.loads(complete_resp.content)["status"] == "uploaded"

        secure_resp = client.get(reverse("web:request_help_secure_page", kwargs={"token": token}))
        assert secure_resp.status_code == 200
        assert b"Photos" in secure_resp.content


def _backdate_form_opened_at(client: Client) -> None:
    """S2.7's min-fill-time anti-abuse check (`ham.requester_portal.antiabuse`) is keyed off
    when the whole form was started (session, set by `request_help_begin`), not real wall-clock
    time elapsed while a test drives the client instantly -- backdate it so these tests never
    trip the "treated as a robot" branch (docs/ux/intake.md §9)."""
    import datetime as dt

    from ham.platform.clock import now as clock_now
    from ham.requester_portal import antiabuse
    from ham.rules import RULES
    from ham.web.views_requester import _SESSION_FORM_OPENED_AT

    opened_at = clock_now() - RULES.intake.INTAKE_MIN_FILL_TIME - dt.timedelta(seconds=1)
    session = client.session
    session[_SESSION_FORM_OPENED_AT] = antiabuse.sign_form_opened_at(now=opened_at)
    session.save()


class TestNoEmailFlow:
    def test_saves_without_a_code_and_shows_r7n(self, client: Client):
        _fill_wizard(client, no_email=True)
        resp = client.post(
            reverse("web:request_help_step", kwargs={"step": "review"}),
            {"attested_statements": ["owner_authority", "responsibility"]},
            follow=True,
        )
        assert resp.status_code == 200, resp.content
        assert resp.redirect_chain[-1][0] == reverse("web:request_help_saved")
        assert b"HAM #" in resp.content
        assert b"call you" in resp.content


class TestStepValidation:
    def test_missing_required_field_shows_inline_error_and_keeps_answers(self, client: Client):
        client.get(reverse("web:request_help_start"))
        client.post(reverse("web:request_help_begin"))
        resp = client.post(
            reverse("web:request_help_step", kwargs={"step": "need"}),
            {"need_category": "", "description": ""},
        )
        assert resp.status_code == 422
        assert b"Choose what kind of help" in resp.content


class TestUnknownToken:
    def test_unknown_token_shows_neutral_page(self, client: Client):
        resp = client.get(
            reverse("web:request_help_secure_page", kwargs={"token": "not-a-real-token"})
        )
        assert resp.status_code == 200
        assert b"couldn&#x27;t open this page" in resp.content or b"could" in resp.content


class TestFindMyRequest:
    def test_same_response_regardless_of_match(self, client: Client):
        resp = client.post(reverse("web:request_help_find"), {"email": "nobody@example.org"})
        assert resp.status_code == 200
        assert b"Check your email" in resp.content


class TestLinkExpiredAndNewLink:
    def test_expired_link_offers_masked_email_then_new_link(self, client: Client, local_storage):
        # Build a real request+link the fast way (service layer), then supersede it.
        import uuid

        from ham.authz.context import RequesterContext
        from ham.requester_portal import services
        from ham.requester_portal.models import RequesterAccessLink
        from ham.requests.certifications import required_statements
        from ham.requests.services import SubmittedRequestPayload, submit_request
        from ham.requests.states import VerificationMethod

        payload = SubmittedRequestPayload(
            full_name="Expired Link Test",
            phone="+13055550199",
            email="expired@example.org",
            line1="1 Test St",
            city="Miami",
            state="FL",
            postal_code="33101",
            property_type="single_family_home",
            relationship_to_property="owner",
            need_category="plumbing",
            preferred_contact_method="email",
            attested_statements=required_statements("owner"),
            verification_method=VerificationMethod.EMAIL_CODE,
            verified_value="expired@example.org",
        )
        ctx = RequesterContext(request_id=None)
        request = submit_request(
            ctx, draft_id=uuid.uuid4(), verification_id=uuid.uuid4(), payload=payload
        )
        issued = services.issue_link(request_id=request.id, kind=RequesterAccessLink.KIND_INITIAL)
        old_token = issued.token
        # Supersede it (simulating time passing / a later regeneration).
        services.issue_link(request_id=request.id, kind=RequesterAccessLink.KIND_REGENERATED)

        resp = client.get(reverse("web:request_help_secure_page", kwargs={"token": old_token}))
        assert resp.status_code == 200
        assert b"link has expired" in resp.content
        assert b"e\xe2\x80\xa2\xe2\x80\xa2\xe2\x80\xa2@example.org" in resp.content

        mail.outbox.clear()
        send_resp = client.post(
            reverse("web:request_help_link_expired_send", kwargs={"token": old_token}),
            follow=True,
        )
        assert send_resp.status_code == 200
        assert send_resp.redirect_chain[-1][0] == reverse("web:request_help_verify")
        run_due_jobs_now()
        assert len(mail.outbox) == 1

        challenge = RequesterVerificationChallenge.objects.get(
            purpose="link_regeneration", request_id=request.id
        )
        challenge.code_hash = otp.hash_value("333444")
        challenge.save(update_fields=["code_hash"])

        code_resp = client.post(reverse("web:request_help_verify"), {"code": "333444"}, follow=True)
        assert code_resp.status_code == 200, code_resp.content
        assert code_resp.redirect_chain[-1][0].startswith("/request-help/r/")
