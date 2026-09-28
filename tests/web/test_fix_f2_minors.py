"""FIX-F2 item 7 (usability re-check Minors 3-4) and item 6 (UX M2 leftover): plain History
wording (version kept in a `title`, not the visible text), church phone formatted on R8/R11b,
and R10 using the canonical `NEED_CATEGORY_LABELS`/`PROPERTY_TYPE_LABELS` (no code-derived
labels). New file per wave brief.
"""

from __future__ import annotations

import uuid

import pytest
from django.test import Client
from django.urls import reverse

from ham.identity.models import RoleAssignment, SharedIdentityProfile
from ham.jobs import run_due_jobs_now
from ham.platform.clock import now as clock_now
from ham.requests.presentation import NEED_CATEGORY_LABELS, PROPERTY_TYPE_LABELS
from ham.requests.queries import request_history

pytestmark = pytest.mark.django_db(transaction=True)


def _login(client, make_user, *, email: str, full_name: str, role: str):
    user = make_user(email)
    SharedIdentityProfile.objects.create(user=user, full_name=full_name)
    RoleAssignment.objects.create(user=user, role=role, granted_at=clock_now())
    client.force_login(user)
    session = client.session
    session["ham_mfa_satisfied"] = True
    session.save()
    return user


def _submitted(**overrides):
    from ham.authz.context import RequesterContext
    from ham.requests.services import submit_request
    from tests.requests.conftest import make_payload

    request = submit_request(
        RequesterContext(request_id=None),
        draft_id=uuid.uuid4(),
        verification_id=uuid.uuid4(),
        payload=make_payload(**overrides),
    )
    # Drains the duplicate-check job `submit_request` deferred, so it doesn't leak into a
    # later test's `run_due_jobs_now()` call.
    run_due_jobs_now()
    return request


class TestHistoryLabelIsPlainWording:
    def test_agreed_to_intake_statements_entry_has_no_version_string_in_the_label(self):
        request = _submitted()
        entries = request_history(request)
        cert_entry = next(e for e in entries if e.label.startswith("Agreed"))
        assert cert_entry.label == "Agreed to the intake statements"
        assert request.attestation_version not in cert_entry.label
        # The version is kept in the record and available as a tooltip, not discarded.
        assert cert_entry.title == request.attestation_version

    def test_l2_page_shows_plain_wording_with_version_only_in_a_title_attribute(
        self, client: Client, make_user
    ):
        request = _submitted()
        _login(
            client,
            make_user,
            email="marcus@example.org",
            full_name="Marcus Bell",
            role="HAM_DIRECTOR",
        )
        resp = client.get(reverse("web:request_detail", args=[request.id]))
        content = resp.content.decode()
        assert "Agreed to the intake statements" in content
        assert f"Agreed to intake statements {request.attestation_version}" not in content
        assert f'title="{request.attestation_version}"' in content


class TestR10UsesCanonicalLabels:
    def test_r10_need_category_and_property_type_match_the_canonical_labels(
        self, client: Client, real_portal_lookups
    ):
        from ham.requester_portal import services

        request = _submitted(need_category="ramps_rails_grab_bars", property_type="house")
        issued = services.issue_link(request_id=request.id, kind="initial")

        resp = client.get(reverse("web:request_help_secure_page", args=[issued.token]))
        assert resp.status_code == 200
        content = resp.content.decode()
        assert NEED_CATEGORY_LABELS["ramps_rails_grab_bars"] in content
        assert PROPERTY_TYPE_LABELS["house"] in content
        # The old code-derived fallback ("Ramps rails grab bars", underscores replaced and
        # capitalized) must not appear -- only the real label.
        assert "Ramps rails grab bars" not in content


class TestChurchPhoneFormattedOnRequesterScreens:
    def _set_church_phone(self) -> None:
        from ham.platform.models import ChurchProfile

        row = ChurchProfile.get_solo()
        row.ham_phone = "+13055550100"
        row.save(update_fields=["ham_phone"])

    def test_r11b_formats_the_church_phone(self, client: Client):
        self._set_church_phone()
        resp = client.post(reverse("web:request_help_find"), {"email": "nobody@example.org"})
        assert resp.status_code == 200
        content = resp.content.decode()
        # The visible text is formatted; the `tel:` href legitimately keeps E.164.
        assert "Call (305) 555-0100" in content
        assert "Call +13055550100" not in content

    def test_r8_formats_the_church_phone(self, client: Client):
        self._set_church_phone()
        from tests.web.test_requester_portal_screens import _fill_wizard

        _fill_wizard(client)
        resp = client.post(
            reverse("web:request_help_step", kwargs={"step": "review"}),
            {"attested_statements": ["owner_authority", "responsibility"]},
            follow=True,
        )
        assert resp.status_code == 200
        content = resp.content.decode()
        # The visible phone text is formatted (the anchor text itself, distinct from the
        # `tel:` href right before it, which legitimately keeps E.164).
        assert 'tel:+13055550100">(305) 555-0100</a>' in content
