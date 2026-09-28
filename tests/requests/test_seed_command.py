from __future__ import annotations

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from ham.requests.models import AssistanceRequest
from ham.requests.states import RequestStatus

pytestmark = pytest.mark.django_db


class TestSeedDevRequests:
    def test_refuses_in_production(self):
        with override_settings(HAM_ENV="production"):
            with pytest.raises(CommandError):
                call_command("seed_dev_requests")
        assert not AssistanceRequest.objects.exists()

    def test_covers_every_status_and_an_urgent_and_no_email_request(self):
        call_command("seed_dev_requests")
        statuses = set(AssistanceRequest.objects.values_list("status", flat=True))
        assert RequestStatus.SUBMITTED.value in statuses
        assert RequestStatus.AWAITING_APPROVAL.value in statuses
        assert RequestStatus.NEEDS_PHONE_CHECK.value in statuses
        assert RequestStatus.CANCELLED.value in statuses
        assert AssistanceRequest.objects.filter(urgent_requested=True).exists()
        assert AssistanceRequest.objects.filter(requester__email__isnull=True).exists()

    def test_only_example_org_emails(self):
        call_command("seed_dev_requests")
        for email in AssistanceRequest.objects.exclude(requester__email__isnull=True).values_list(
            "requester__email", flat=True
        ):
            assert email.endswith("@example.org")
