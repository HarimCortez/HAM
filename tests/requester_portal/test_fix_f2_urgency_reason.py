"""FIX-F2 item 1 (UX M4 + N-M1): `urgency_reason` is its own field, never composed/prefixed
onto `urgency_justification`. New file per wave brief.
"""

from __future__ import annotations

import uuid

import pytest
from django.test import Client
from django.urls import reverse

from ham.jobs import run_due_jobs_now
from ham.platform import otp
from ham.requester_portal.models import RequesterVerificationChallenge
from ham.requests.models import AssistanceRequest
from ham.requests.presentation import urgency_line
from tests.web.test_requester_portal_screens import _backdate_form_opened_at, _step_payload

pytestmark = pytest.mark.django_db(transaction=True)


class TestNeverPrefixedOnResave:
    """Before the fix: `views_requester._need_data` composed
    `f"{label}. {justification}"` into `urgency_justification` on every POST of the "need"
    step, so re-editing and re-submitting the same step duplicated the label
    ("Label. Label. text"). This drives the view directly (not the draft-level helper) since
    that is exactly where the bug lived."""

    def test_resubmitting_the_need_step_never_duplicates_the_reason_label(self, client: Client):
        client.get(reverse("web:request_help_start"))
        client.post(reverse("web:request_help_begin"), follow=True)
        _backdate_form_opened_at(client)

        need_data = {
            "need_category": "roof_or_ceiling",
            "description": "Water leaks in.",
            "urgent_requested": "1",
            "urgency_reason": "water_or_damage",
            "urgency_justification": "It is getting worse every hour.",
        }
        resp = client.post(
            reverse("web:request_help_step", kwargs={"step": "need"}), need_data, follow=True
        )
        assert resp.status_code == 200, resp.content

        # Re-submit the exact same step again (as if the person went Back and hit Continue a
        # second time) -- the stored justification must be byte-for-byte the same, never
        # re-prefixed with the reason's label.
        resp = client.post(
            reverse("web:request_help_step", kwargs={"step": "need"}), need_data, follow=True
        )
        assert resp.status_code == 200, resp.content

        resp = client.get(reverse("web:request_help_step", kwargs={"step": "need"}))
        content = resp.content.decode()
        assert content.count("It is getting worse every hour.") == 1
        assert "Water is coming in or damage is getting worse. Water is coming in" not in content


class TestRequestSubmitStoresReasonSeparately:
    def test_submitted_request_keeps_reason_and_justification_as_two_fields(
        self, client: Client, real_portal_lookups
    ):
        client.get(reverse("web:request_help_start"))
        client.post(reverse("web:request_help_begin"), follow=True)
        _backdate_form_opened_at(client)

        steps = _step_payload()
        need_data = dict(steps["need"])
        need_data["urgent_requested"] = "1"
        need_data["urgency_reason"] = "water_or_damage"
        need_data["urgency_justification"] = "It is getting worse."
        client.post(
            reverse("web:request_help_step", kwargs={"step": "need"}), need_data, follow=True
        )
        client.post(
            reverse("web:request_help_step", kwargs={"step": "home"}), steps["home"], follow=True
        )
        client.post(
            reverse("web:request_help_step", kwargs={"step": "safety"}),
            steps["safety"],
            follow=True,
        )
        client.post(
            reverse("web:request_help_step", kwargs={"step": "reaching-you"}),
            steps["reaching-you"],
            follow=True,
        )
        resp = client.post(
            reverse("web:request_help_step", kwargs={"step": "review"}),
            {"attested_statements": ["owner_authority", "responsibility"]},
            follow=True,
        )
        assert resp.status_code == 200, resp.content
        assert resp.redirect_chain[-1][0] == reverse("web:request_help_verify")

        challenge = RequesterVerificationChallenge.objects.get(purpose="intake")
        challenge.code_hash = otp.hash_value("246810")
        challenge.save(update_fields=["code_hash"])
        code_resp = client.post(reverse("web:request_help_verify"), {"code": "246810"}, follow=True)
        assert code_resp.status_code == 200, code_resp.content
        # Drains the duplicate-check job `submit_request` deferred, so it doesn't leak into a
        # later test's `run_due_jobs_now()` call (same convention as
        # `TestFullEmailFlow.test_form_to_secure_page_and_one_photo`).
        run_due_jobs_now()

        request = AssistanceRequest.objects.get()
        assert request.urgency_reason == "water_or_damage"
        assert request.urgency_justification == "It is getting worse."


class TestUrgencyLineComposition:
    def test_composes_label_then_justification(self):
        assert (
            urgency_line("water_or_damage", "It is getting worse.")
            == "Water is coming in or damage is getting worse. It is getting worse."
        )

    def test_reason_only_no_trailing_period_soup(self):
        assert urgency_line("no_utilities", "") == "No power, water, heat or cooling"

    def test_unknown_reason_code_falls_back_to_justification(self):
        assert urgency_line("", "Just urgent, trust me.") == "Just urgent, trust me."


class TestUrgencyReasonKeptAtRetentionPurge:
    def test_reason_code_survives_the_7_year_purge_but_justification_is_erased(self):
        """Item 1: `urgency_reason` is a code, not free text -- kept at the 7-year retention
        purge, unlike `urgency_justification` (Q-145)."""
        from ham.authz.context import RequesterContext, SystemContext
        from ham.requests.services import purge_expired_request, submit_request
        from ham.requests.states import CancelReason
        from tests.requests.conftest import make_payload

        request = submit_request(
            RequesterContext(request_id=None),
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(
                urgent_requested=True,
                urgency_reason="someone_could_get_hurt",
                urgency_justification="Loose railing.",
            ),
        )
        run_due_jobs_now()  # drain the deferred duplicate-check job before it leaks

        request.cancel_reason_code = CancelReason.REQUESTER_WITHDREW.value
        request.closed_at = request.submitted_at
        request.save(update_fields=["cancel_reason_code", "closed_at"])

        purge_expired_request(SystemContext(), request_id=request.id)
        request.refresh_from_db()
        assert request.urgency_reason == "someone_could_get_hurt"
        assert request.urgency_justification == ""
