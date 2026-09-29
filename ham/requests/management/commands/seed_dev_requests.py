"""manage.py seed_dev_requests

Fictional example.org requests covering every step-2 status, including one urgent request
and one with no email at all (Q-025 -- held in NEEDS_PHONE_CHECK). For local development and
Playwright smoke tests (foundation.md §2.11 conventions). Refuses to run when
`HAM_ENV=production`.

Creates rows directly (like `ham.identity.management.commands.seed_dev`) rather than through
`submit_request`, since that command needs a verified `IntakeDraft`/challenge from
`ham.requester_portal` (a parallel, possibly-unbuilt slice in any given worktree) -- a seed
command's job is realistic *data*, not exercising the verification flow.
"""

from __future__ import annotations

import datetime as dt

from django.core.management.base import BaseCommand
from django.db import transaction

from ham.platform.clock import now as clock_now
from ham.platform.env import refuse_in_production
from ham.platform.otp import hash_value
from ham.requests import certifications
from ham.requests.matching import match_keys
from ham.requests.models import (
    AssistanceRequest,
    NeedCategory,
    PreferredContactMethod,
    Property,
    PropertyType,
    RelationshipToProperty,
    RequestContactVerification,
    Requester,
    RequestSource,
    UrgencyReason,
    next_reference_number,
)
from ham.requests.states import CancelReason, RequestStatus, UrgencyStatus, VerificationMethod


def _hashed_keys(*, full_name, email, phone, line1, postal_code):
    keys = match_keys(
        full_name=full_name,
        email=email,
        phone=phone,
        line1=line1,
        line2="",
        postal_code=postal_code,
    )
    return {
        "email_key": hash_value(keys.email) if keys.email else None,
        "phone_key": hash_value(keys.phone) if keys.phone else None,
        "name_zip_key": hash_value(keys.name_zip) if keys.name_zip else None,
        "address_key": hash_value(keys.address) if keys.address else None,
    }


class Command(BaseCommand):
    help = (
        "Create fictional example.org requests covering every step-2 status, for local "
        "development and Playwright smoke tests. Refuses to run when HAM_ENV=production."
    )

    def handle(self, *args, **options):
        refuse_in_production("seed_dev_requests")

        now = clock_now()
        with transaction.atomic():
            self._create(
                need_category=NeedCategory.PLUMBING_OR_WATER,
                status=RequestStatus.SUBMITTED,
                full_name="Doris Hall",
                email="doris@example.org",
                phone="+13055550101",
                submitted_at=now - dt.timedelta(hours=2),
            )
            self._create(
                need_category=NeedCategory.ROOF_OR_CEILING,
                status=RequestStatus.AWAITING_APPROVAL,
                full_name="Walter Jimenez",
                email="walter@example.org",
                phone="+13055550102",
                submitted_at=now - dt.timedelta(days=1),
            )
            self._create(
                need_category=NeedCategory.ELECTRICAL,
                status=RequestStatus.AWAITING_APPROVAL,
                full_name="Priya Nair",
                email="priya@example.org",
                phone="+13055550103",
                submitted_at=now - dt.timedelta(hours=6),
                urgent=True,
                urgency_reason=UrgencyReason.SOMETHING_ELSE,
                urgency_justification="Exposed wiring near a bathtub.",
            )
            self._create(
                need_category=NeedCategory.RAMPS_RAILS_GRAB_BARS,
                status=RequestStatus.NEEDS_PHONE_CHECK,
                full_name="Ruth Hall",
                email=None,
                phone="+13055550177",
                submitted_at=now - dt.timedelta(days=1, hours=1),
                email_opt_out=True,
            )
            self._create(
                need_category=NeedCategory.PAINTING_OR_WALLS,
                status=RequestStatus.CANCELLED,
                full_name="Test Testerson",
                email="spam@example.org",
                phone="+13055550199",
                submitted_at=now - dt.timedelta(days=10),
                cancel_reason=CancelReason.SPAM,
            )
            self._create(
                need_category=NeedCategory.YARD_OR_OUTSIDE,
                status=RequestStatus.CANCELLED,
                full_name="Grace Okafor",
                email="grace.o@example.org",
                phone="+13055550188",
                submitted_at=now - dt.timedelta(days=5),
                cancel_reason=CancelReason.REQUESTER_WITHDREW,
            )
        self.stdout.write(self.style.SUCCESS("Seeded fictional example.org requests."))

    def _create(
        self,
        *,
        need_category,
        status: RequestStatus,
        full_name: str,
        email: str | None,
        phone: str,
        submitted_at: dt.datetime,
        urgent: bool = False,
        urgency_reason: UrgencyReason | str = "",
        urgency_justification: str = "",
        email_opt_out: bool = False,
        cancel_reason: CancelReason | None = None,
    ) -> AssistanceRequest:
        relationship = RelationshipToProperty.OWNER
        # S3.0: `req_closed_at_set_when_cancelled` is now a real (not tautological) CHECK, so
        # a CANCELLED row must carry `closed_at` from the very first INSERT -- creating it
        # open and closing it in a follow-up `.save()` (the old two-step shape below) would
        # violate the constraint on the initial insert itself.
        is_cancelled = status is RequestStatus.CANCELLED
        closed_at = submitted_at + dt.timedelta(hours=1) if is_cancelled else None
        cancel_reason_code = (cancel_reason or CancelReason.SPAM).value if is_cancelled else ""
        request = AssistanceRequest.objects.create(
            reference_number=next_reference_number(),
            status=status.value,
            source=RequestSource.PUBLIC_FORM,
            need_category=need_category,
            description="Fictional dev-seed request -- see seed_dev_requests.",
            urgent_requested=urgent,
            urgency_reason=urgency_reason,
            urgency_justification=urgency_justification,
            urgency_status=(
                UrgencyStatus.AWAITING_CERTIFICATION.value if urgent else UrgencyStatus.NONE.value
            ),
            preferred_contact_method=PreferredContactMethod.PHONE_CALL
            if email is None
            else PreferredContactMethod.EMAIL,
            relationship_to_property=relationship,
            attestation_version=certifications.ATTESTATION_VERSION,
            attested_statements=list(certifications.required_statements(relationship)),
            attested_at=submitted_at,
            submitted_at=submitted_at,
            status_changed_at=submitted_at,
            closed_at=closed_at,
            cancel_reason_code=cancel_reason_code,
        )

        keys = _hashed_keys(
            full_name=full_name,
            email=email,
            phone=phone,
            line1="100 Fictional Ave",
            postal_code="33101",
        )
        Requester.objects.create(
            request=request,
            full_name=full_name,
            email=email,
            phone=phone,
            email_key=keys["email_key"],
            phone_key=keys["phone_key"],
            name_zip_key=keys["name_zip_key"],
        )
        Property.objects.create(
            request=request,
            line1="100 Fictional Ave",
            city="Example City",
            state="FL",
            postal_code="33101",
            property_type=PropertyType.HOUSE,
            address_key=keys["address_key"],
        )
        if email is not None:
            RequestContactVerification.objects.create(
                request=request,
                channel="email",
                method=VerificationMethod.EMAIL_CODE.value,
                value_key=hash_value(email),
                purpose="intake",
                verified_at=submitted_at,
            )
        elif email_opt_out and status is not RequestStatus.NEEDS_PHONE_CHECK:
            pass  # already verified by phone in a real flow; the seed keeps it simple
        return request
