"""FIX-G UX minors: national phone formatting and graceful omission in requester emails, the
"use the button below" wording fix, the neutral already-received page's lead/church-phone/
demoted "Ask for help", the new-link confirm page's tab title, and the R11b honeypot field.
"""

from __future__ import annotations

import re

import pytest
from django.core import mail
from django.test import Client
from django.urls import reverse

from ham.jobs import run_due_jobs_now
from ham.platform.church import church_profile
from tests.web.test_requester_portal_screens import _fill_wizard

pytestmark = pytest.mark.django_db(transaction=True)

_LINK_RE = re.compile(r"/request-help/verify/link/([^\s]+)")


def _submit_and_get_code_email(client: Client) -> str:
    mail.outbox.clear()
    _fill_wizard(client)
    resp = client.post(
        reverse("web:request_help_step", kwargs={"step": "review"}),
        {"attested_statements": ["owner_authority", "responsibility"]},
        follow=True,
    )
    assert resp.status_code == 200, resp.content
    run_due_jobs_now()
    assert len(mail.outbox) == 1
    return str(mail.outbox[0].body)


class TestCodeEmailWording:
    def test_code_email_never_says_use_the_button_below(self):
        body = _submit_and_get_code_email(Client())
        assert "use the button below" not in body.lower()
        assert "open this link" in body.lower()


class TestRequestReceivedEmailContactLine:
    def test_omits_missing_phone_and_email_gracefully(self, db):
        from ham.platform.models import ChurchProfile

        row = ChurchProfile.get_solo()
        row.ham_phone = ""
        row.ham_email = ""
        row.save(update_fields=["ham_phone", "ham_email"])

        # No code-email assertion here matters; this test only needs the contact-line
        # builder itself, exercised directly (cheaper and more precise than a full submit).
        from ham.requester_portal.notifications import _contact_line

        assert _contact_line(church_profile()) == ""


class TestAlreadyReceivedNeutralPage:
    def test_leads_with_check_email_and_offers_a_formatted_phone_call(self, client: Client):
        from ham.platform.models import ChurchProfile

        row = ChurchProfile.get_solo()
        row.ham_phone = "+13055550142"
        row.save(update_fields=["ham_phone"])

        body = _submit_and_get_code_email(client)
        match = _LINK_RE.search(body)
        assert match is not None
        token = match.group(1)

        # Consume the link on a different browser first so it becomes "already used".
        other = Client()
        first = other.post(reverse("web:request_help_verify_link", kwargs={"token": token}))
        assert first.status_code in (200, 302)
        run_due_jobs_now()

        second = other.post(reverse("web:request_help_verify_link", kwargs={"token": token}))
        html = second.content.decode()
        assert "Check your email for the link to your request page" in html
        assert "(305) 555-0142" in html
        # "Ask for help" is present but demoted (secondary styling), not the lead action.
        lead_index = html.index("Check your email for the link to your request page")
        ask_index = html.index("Ask for help")
        assert ask_index > lead_index


class TestNewLinkConfirmPageTitle:
    def test_title_matches_new_link_purpose(self, db):
        # A direct GET at a `new_link`-kind confirm page (any token -- even an unknown one,
        # since the title reflects the *purpose* of the page, not whether this particular
        # token happens to be valid) titles itself for that purpose, not the generic "Confirm
        # your request" (intake) title.
        resp = Client().get(
            reverse("web:request_help_new_link", kwargs={"token": "not-a-real-token"})
        )
        assert resp.status_code == 200
        html = resp.content.decode()
        assert "<title>Open your request" in html
        assert "<title>Confirm your request" not in html


class TestR11bHoneypot:
    def test_honeypot_field_present_and_trips_silently(self, client: Client):
        get_resp = client.get(reverse("web:request_help_find"))
        assert get_resp.status_code == 200
        html = get_resp.content.decode()
        assert 'name="organization_website"' in html

        mail.outbox.clear()
        post_resp = client.post(
            reverse("web:request_help_find"),
            {"email": "someone@example.org", "organization_website": "http://spam.example"},
        )
        assert post_resp.status_code == 200
        assert "Check your email" in post_resp.content.decode()
        run_due_jobs_now()
        assert mail.outbox == []  # tripped the honeypot -- nothing sent, same-looking response
