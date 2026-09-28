"""FIX-F2 item 4 (UX M8): confirming a code/link after the draft was already submitted
(another device, a reused link) never invites a duplicate request. Session-backed R8 (proof
this browser holds the draft's own session) reveals the HAM # and a way in; a bare
already-used link (no such proof) shows a neutral message only. New file per wave brief.
"""

from __future__ import annotations

import re

import pytest
from django.core import mail
from django.test import Client
from django.urls import reverse

from ham.jobs import run_due_jobs_now
from ham.requester_portal.models import RequesterVerificationChallenge
from tests.web.test_requester_portal_screens import _fill_wizard

pytestmark = pytest.mark.django_db(transaction=True)

_LINK_RE = re.compile(r"/request-help/verify/link/([^\s]+)")


def _start_and_reach_r8(client: Client) -> None:
    _fill_wizard(client)
    resp = client.post(
        reverse("web:request_help_step", kwargs={"step": "review"}),
        {"attested_statements": ["owner_authority", "responsibility"]},
        follow=True,
    )
    assert resp.status_code == 200, resp.content


class TestR8AfterAnotherDeviceAlreadyConfirmed:
    """The "Angela" scenario: confirms via the emailed link on her phone, then types a wrong
    code (the real challenge is already consumed -- another device spent it) on her laptop.

    FIX-G NH1: a session that still names this draft id is NOT proof of anything by itself --
    no correct code was ever entered on this browser. This must show the same neutral message
    as a truly unknown code, never the HAM # (see `TestConfirmLinkAlreadyUsedIsNeutralFor
    AnUnverifiedBrowser` below for the equivalent link-replay case) -- but it also must never
    say "start again" (which would invite a duplicate submission)."""

    def test_r8_after_other_device_confirms_shows_neutral_message_not_start_again(
        self, client: Client
    ):
        mail.outbox.clear()
        _start_and_reach_r8(client)
        run_due_jobs_now()
        assert len(mail.outbox) == 1
        match = _LINK_RE.search(str(mail.outbox[0].body))
        assert match is not None
        token = match.group(1)

        # A second device (phone) opens and confirms the emailed link first.
        phone = Client()
        confirm_resp = phone.post(
            reverse("web:request_help_verify_link", kwargs={"token": token}), follow=True
        )
        assert confirm_resp.status_code == 200
        assert b"HAM #" in confirm_resp.content
        # Drains the duplicate-check job `submit_request` deferred, so it doesn't leak into a
        # later test's `run_due_jobs_now()` call.
        run_due_jobs_now()

        # Back on the original browser (laptop): its own session still has the pending code
        # entry for this exact draft, but this POST's own code is wrong -- nothing was just
        # proven on THIS browser.
        code_resp = client.post(reverse("web:request_help_verify"), {"code": "000000"})
        assert code_resp.status_code == 200
        content = code_resp.content.decode()
        assert "Already received" in content
        assert "HAM #" not in content
        assert "/request-help/r/" not in content
        assert "please start again" not in content.lower()
        assert "please try again" not in content.lower()


class TestConfirmLinkAlreadyUsedIsNeutralForAnUnverifiedBrowser:
    """Two taps on the same emailed link (or the same link opened later by anyone else who
    merely has the URL text) -- the second visitor never proved anything beyond having the
    URL, so no HAM # or direct link is shown."""

    def test_second_visit_to_an_already_used_link_shows_neutral_message_only(self, client: Client):
        mail.outbox.clear()
        _start_and_reach_r8(client)
        run_due_jobs_now()
        match = _LINK_RE.search(str(mail.outbox[0].body))
        assert match is not None
        token = match.group(1)

        first = Client()
        first_resp = first.post(
            reverse("web:request_help_verify_link", kwargs={"token": token}), follow=True
        )
        assert first_resp.status_code == 200
        assert b"HAM #" in first_resp.content
        run_due_jobs_now()

        second = Client()
        second_resp = second.post(reverse("web:request_help_verify_link", kwargs={"token": token}))
        assert second_resp.status_code == 200
        content = second_resp.content.decode()
        assert "Already received" in content
        assert "HAM #" not in content
        assert "Open my request page" not in content
        assert "please start again" not in content.lower()

        # A GET (e.g. re-opening the same emailed link) is just as neutral.
        second_get = second.get(reverse("web:request_help_verify_link", kwargs={"token": token}))
        assert second_get.status_code == 200
        get_content = second_get.content.decode()
        assert "Already received" in get_content
        assert "HAM #" not in get_content


class TestFallbackWordingNeverInvitesADuplicate:
    def test_generic_no_challenge_error_says_send_a_new_code_not_start_again(self, client: Client):
        """A genuinely stale/unknown code entry (this draft never became a request at all)
        still gets a recovery message that keeps the draft, never "please start again"."""
        _start_and_reach_r8(client)
        challenge = RequesterVerificationChallenge.objects.get(purpose="intake")
        # Consume it directly (as if entered correctly once already) so a second attempt with
        # any code finds nothing to check against, without this draft ever becoming a request.
        challenge.consumed_at = challenge.created_at
        challenge.save(update_fields=["consumed_at"])

        resp = client.post(reverse("web:request_help_verify"), {"code": "999999"})
        assert resp.status_code == 422
        content = resp.content.decode()
        assert "please start again" not in content.lower()
        assert "send a new code" in content.lower()
