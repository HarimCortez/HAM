"""Minimal real AssistanceRequest rows for media tests (no requester/property needed)."""

from __future__ import annotations

from ham.platform.clock import now as clock_now
from ham.requests.models import AssistanceRequest, NeedCategory, next_reference_number
from ham.requests.states import RequestStatus


def create_request(
    *, status: str = RequestStatus.SUBMITTED.value, closed_at=None
) -> AssistanceRequest:
    now = clock_now()
    return AssistanceRequest.objects.create(
        reference_number=next_reference_number(),
        status=status,
        need_category=NeedCategory.values[0],
        preferred_contact_method=AssistanceRequest._meta.get_field(
            "preferred_contact_method"
        ).choices[0][0],  # type: ignore[index]
        relationship_to_property=AssistanceRequest._meta.get_field(
            "relationship_to_property"
        ).choices[0][0],  # type: ignore[index]
        attestation_version="test",
        submitted_at=now,
        status_changed_at=now,
        closed_at=closed_at,
    )
