"""`requests_request`, `requests_requester`, `requests_property`,
`requests_contact_verification`, `requests_match` (intake.md §3). S2.2.

Field classes (intake.md §3): **P** identity/contact (reveal-gated, never in lists/logs/
outbox/AI/aggregates), **C** circumstances (detail page only, to `request.view` holders),
**S** other sensitive values (keys). Never add a **P**/**C** field to a list/queryset used by
`ham.requests.queries.list_requests` or any outbox payload.
"""

from __future__ import annotations

from django.contrib.postgres.fields import ArrayField
from django.db import connection, models

from ham.platform.ids import UUID7Field
from ham.requests.states import CancelReason, RequestStatus, UrgencyStatus, VerificationMethod

REFERENCE_NUMBER_SEQUENCE = "requests_reference_number_seq"


def next_reference_number() -> int:
    """The next "HAM #" (intake.md §3: "int, unique, from a Postgres sequence"). Called once
    per submission, inside the same transaction as the row insert."""
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT nextval('{REFERENCE_NUMBER_SEQUENCE}')")
        (value,) = cursor.fetchone()
    return int(value)


class NeedCategory(models.TextChoices):
    """PRD-GAP Q-107: proposed default in use; owner may change (intake.md §3)."""

    PLUMBING = "plumbing", "Plumbing"
    ELECTRICAL = "electrical", "Electrical"
    ROOF = "roof", "Roof"
    CARPENTRY = "carpentry", "Carpentry & repairs"
    ACCESSIBILITY = "accessibility", "Accessibility"
    PAINTING = "painting", "Painting"
    YARD_OUTDOOR = "yard_outdoor", "Yard & outdoor"
    OTHER = "other", "Other"


class RelationshipToProperty(models.TextChoices):
    OWNER = "owner", "Owner"
    AUTHORIZED_FAMILY_MEMBER = "authorized_family_member", "Authorized family member"
    TENANT = "tenant", "Tenant"


class PropertyType(models.TextChoices):
    SINGLE_FAMILY_HOME = "single_family_home", "Single-family home"
    MOBILE_MANUFACTURED_HOME = "mobile_manufactured_home", "Mobile / manufactured home"
    TOWNHOME_CONDO = "townhome_condo", "Townhome / condominium"
    APARTMENT = "apartment", "Apartment"
    OTHER = "other", "Other"


class PreferredContactMethod(models.TextChoices):
    """Q-124 (decided): stored as a preference for leaders; HAM's own automatic messages go
    by email regardless (§75 -- no SMS provider in V1)."""

    EMAIL = "email", "Email"
    PHONE_CALL = "phone_call", "Phone call"
    TEXT_MESSAGE = "text_message", "Text message"


class RequestSource(models.TextChoices):
    PUBLIC_FORM = "public_form", "Public form"
    CHURCH_LINK = "church_link", "Church-issued link"
    ASSISTED = "assisted", "Entered on someone's behalf"


class AssistanceRequest(models.Model):
    id = UUID7Field()
    reference_number = models.PositiveIntegerField(unique=True, editable=False)
    status = models.CharField(
        max_length=32,
        choices=[(s.value, s.value) for s in RequestStatus],
        default=RequestStatus.SUBMITTED.value,
    )
    source = models.CharField(
        max_length=16, choices=RequestSource.choices, default=RequestSource.PUBLIC_FORM
    )
    intake_source_id = models.UUIDField(null=True, blank=True)
    created_by_user_id = models.UUIDField(null=True, blank=True)  # assisted entry only

    need_category = models.CharField(max_length=16, choices=NeedCategory.choices)
    description = models.TextField(blank=True, default="")  # C

    urgent_requested = models.BooleanField(default=False)
    urgency_justification = models.TextField(blank=True, default="")  # C
    urgency_status = models.CharField(
        max_length=24,
        choices=[(s.value, s.value) for s in UrgencyStatus],
        default=UrgencyStatus.NONE.value,
    )

    known_hazards = models.TextField(blank=True, default="")  # C
    preferred_availability = models.TextField(blank=True, default="")  # C
    preferred_contact_method = models.CharField(
        max_length=16, choices=PreferredContactMethod.choices
    )
    relationship_to_property = models.CharField(
        max_length=32, choices=RelationshipToProperty.choices
    )

    attestation_version = models.CharField(max_length=32)
    attested_statements = ArrayField(models.CharField(max_length=64), default=list)
    attested_at = models.DateTimeField(null=True, blank=True)

    submitted_at = models.DateTimeField()
    status_changed_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)
    requester_access_ends_at = models.DateTimeField(null=True, blank=True)
    cancel_reason_code = models.CharField(
        max_length=24, choices=[(c.value, c.value) for c in CancelReason], blank=True, default=""
    )
    cancel_note = models.TextField(blank=True, default="")  # C

    class Meta:
        db_table = "requests_request"
        indexes = [
            models.Index(
                fields=["status", "urgent_requested", "submitted_at"], name="req_status_urg_idx"
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(urgent_requested=False, urgency_justification="")
                    | models.Q(urgent_requested=True) & ~models.Q(urgency_justification="")
                ),
                name="req_urgency_justification_iff_urgent",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(closed_at__isnull=True)
                    | ~models.Q(status=RequestStatus.CANCELLED.value)
                    | models.Q(closed_at__isnull=False)
                ),
                name="req_closed_at_when_terminal",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial; never logged (no PII here anyway)
        return f"HAM #{self.reference_number:03d}"

    @property
    def display_number(self) -> str:
        return f"HAM #{self.reference_number:03d}"


class Requester(models.Model):
    """1:1 with the request; not a `User` (intake.md §3)."""

    request = models.OneToOneField(
        AssistanceRequest, on_delete=models.CASCADE, primary_key=True, related_name="requester"
    )
    full_name = models.CharField(max_length=200)  # P
    # DJ001: intentionally nullable, not "" -- NULL means "chose 'I don't use email'" (Q-025),
    # distinct from a match key that simply couldn't be computed.
    email = models.EmailField(null=True, blank=True)  # noqa: DJ001 -- P, opted out = NULL
    phone = models.CharField(max_length=32)  # P, E.164

    # S: keyed-hashed (ham.platform.otp HMAC) normalized match keys -- never the raw value.
    # DJ001: NULL (not "") means "no reliable key could be computed" (matching.py never
    # treats an empty string as a key); an empty string would wrongly match every other
    # un-keyable row against each other.
    email_key = models.CharField(max_length=64, null=True, blank=True, db_index=True)  # noqa: DJ001
    phone_key = models.CharField(max_length=64, null=True, blank=True, db_index=True)  # noqa: DJ001
    name_zip_key = models.CharField(  # noqa: DJ001
        max_length=64, null=True, blank=True, db_index=True
    )

    anonymized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "requests_requester"

    def __str__(self) -> str:  # pragma: no cover - never logged (PII)
        return f"Requester(request={self.request_id})"


class Property(models.Model):
    """1:1 with the request (intake.md §3)."""

    request = models.OneToOneField(
        AssistanceRequest, on_delete=models.CASCADE, primary_key=True, related_name="property"
    )
    line1 = models.CharField(max_length=200)  # P
    line2 = models.CharField(max_length=200, blank=True, default="")  # P
    city = models.CharField(max_length=100)  # P
    state = models.CharField(max_length=2)
    postal_code = models.CharField(max_length=10)  # P
    property_type = models.CharField(max_length=32, choices=PropertyType.choices)
    owner_name = models.CharField(max_length=200, blank=True, default="")  # P (family member)

    address_key = models.CharField(  # noqa: DJ001 -- S, see Requester's match-key comment
        max_length=64, null=True, blank=True, db_index=True
    )

    class Meta:
        db_table = "requests_property"

    def __str__(self) -> str:  # pragma: no cover - never logged (PII)
        return f"Property(request={self.request_id})"


class AppendOnlyError(RuntimeError):
    """Raised by the Python-level guard on `RequestContactVerification` (no DB trigger here,
    unlike `AuditEvent` -- see ham-backend-engineer memory: a `BEFORE TRUNCATE` trigger on an
    append-only table breaks `pytest-django`'s `transaction=True` flush globally without a
    separate, lower-privilege DB role this sandbox doesn't have)."""


class RequestContactVerification(models.Model):
    """Append-only (Python-level guard): every code/link verification and staff phone
    verification for a request (intake.md §3)."""

    id = UUID7Field()
    request = models.ForeignKey(
        AssistanceRequest, on_delete=models.CASCADE, related_name="contact_verifications"
    )
    channel = models.CharField(max_length=8, choices=[("email", "Email"), ("phone", "Phone")])
    method = models.CharField(
        max_length=24, choices=[(m.value, m.value) for m in VerificationMethod]
    )
    value_key = models.CharField(max_length=64)  # S: HMAC of the verified value
    purpose = models.CharField(
        max_length=24,
        choices=[("intake", "Intake"), ("link_regeneration", "Link regeneration")],
        default="intake",
    )
    verified_at = models.DateTimeField()
    verified_by_user_id = models.UUIDField(null=True, blank=True)  # staff only
    challenge_id = models.UUIDField(null=True, blank=True)  # ham.requester_portal's own id

    class Meta:
        db_table = "requests_contact_verification"
        indexes = [models.Index(fields=["request", "verified_at"], name="reqcv_request_idx")]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"RequestContactVerification({self.request_id}, {self.method})"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AppendOnlyError(
                "RequestContactVerification is append-only (intake.md §3); create a new row, "
                "never update an existing one."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AppendOnlyError("RequestContactVerification rows are never deleted.")


class RequestMatch(models.Model):
    """A possible-duplicate flag (PRD §9; Q-109/Q-115). Never dismissed in V1."""

    id = UUID7Field()
    request = models.ForeignKey(AssistanceRequest, on_delete=models.CASCADE, related_name="matches")
    prior_request = models.ForeignKey(
        AssistanceRequest, on_delete=models.CASCADE, related_name="matched_by"
    )
    reasons = ArrayField(models.CharField(max_length=16))
    detected_at = models.DateTimeField()

    class Meta:
        db_table = "requests_match"
        constraints = [
            models.UniqueConstraint(
                fields=["request", "prior_request"], name="reqmatch_unique_pair"
            )
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"RequestMatch({self.request_id} ~ {self.prior_request_id})"
