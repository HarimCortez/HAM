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
    """Q-109 (proposed default in use, docs/ux/intake.md R2 / §12.1 "What kind of help?"):
    the ONE vocabulary for need category, used by both the public form and every leadership
    screen (PRD-guardian M1/UX M2 — there used to be a second, different-coded copy of this
    list in `ham.requester_portal.choices`; that copy is gone, this is the only one)."""

    # PRD-GAP Q-109: leader-initiated category *change* (audited) is deferred to step 3 — this
    # slice only stores the requester's own choice; no "Change category" leadership action
    # exists yet in ham.requests.services.
    ROOF_OR_CEILING = "roof_or_ceiling", "Roof or ceiling"
    PLUMBING_OR_WATER = "plumbing_or_water", "Plumbing or water"
    ELECTRICAL = "electrical", "Electrical"
    DOORS_WINDOWS_LOCKS = "doors_windows_locks", "Doors, windows or locks"
    FLOORS_OR_STAIRS = "floors_or_stairs", "Floors or stairs"
    RAMPS_RAILS_GRAB_BARS = "ramps_rails_grab_bars", "Ramps, rails or grab bars"
    PAINTING_OR_WALLS = "painting_or_walls", "Painting or walls"
    YARD_OR_OUTSIDE = "yard_or_outside", "Yard or outside"
    SOMETHING_ELSE = "something_else", "Something else or not sure"


class RelationshipToProperty(models.TextChoices):
    OWNER = "owner", "Owner"
    AUTHORIZED_FAMILY_MEMBER = "authorized_family_member", "Authorized family member"
    TENANT = "tenant", "Tenant"


class PropertyType(models.TextChoices):
    """Q-110 (proposed default in use, docs/ux/intake.md R3 / §12.1 "Type of home"): the ONE
    vocabulary for property type (see `NeedCategory`'s docstring above for why there is only
    one now)."""

    HOUSE = "house", "House"
    TOWNHOUSE = "townhouse", "Townhouse"
    APARTMENT_OR_CONDO = "apartment_or_condo", "Apartment or condo"
    MOBILE_OR_MANUFACTURED_HOME = "mobile_or_manufactured_home", "Mobile or manufactured home"
    OTHER = "other", "Other"


class PreferredContactMethod(models.TextChoices):
    """Q-111 (proposed default in use; PRD-guardian N1 fixed a wrong Q-124 citation here):
    Email · Phone call only -- the form never offers a "text message" option (§75, no SMS
    provider in V1), so `TEXT_MESSAGE` is gone, not just unoffered."""

    EMAIL = "email", "Email"
    PHONE_CALL = "phone_call", "Phone call"


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

    need_category = models.CharField(max_length=32, choices=NeedCategory.choices)
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
    # PRD-GAP Q-148: proposed default in use; owner may change. R5's "Anything else about
    # reaching you or visiting?" (helper name, best time to call) -- stored and shown to
    # leadership on the detail view and the phone-check screen; erased at the 7-year purge
    # along with the other free-text circumstances. PRD-GAP Q-145: proposed default in use;
    # owner may change (erasing free-text circumstances at 7 years).
    contact_note = models.TextField(blank=True, default="")  # C
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
    # PRD-guardian N8: recorded once, the first time `system.request.complete_intake_checks`
    # moves a request into AWAITING_APPROVAL, and never cleared afterwards -- so
    # `ham.requests.queries.request_history`'s "Awaiting Approval (automatic)" entry keeps
    # showing on the timeline even after the request is later cancelled (`request.status` is
    # no longer AWAITING_APPROVAL at that point, so the old "current status" check silently
    # dropped this entry from the history of every cancelled request).
    awaiting_approval_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    # PRD-guardian N8: who closed it (set by `request.cancel`) -- the history timeline showed
    # no actor at all for a close before this.
    closed_by_user_id = models.UUIDField(null=True, blank=True)
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


class RequestContactVerificationManager(models.Manager):
    """N4: the 7-year retention purge's one exception to "append-only, never bulk-updated" --
    see `erase_value_keys_for_retention`'s own docstring."""

    def erase_value_keys_for_retention(self, request: AssistanceRequest) -> int:
        """Q-145's 7-year purge sweep: blanks every row's hashed `value_key` for ``request``.
        A queryset `.update()` legitimately bypasses `RequestContactVerification.save()`'s own
        append-only guard here -- Django's bulk `.update()` never calls `Model.save()`, which
        is exactly what a genuine system-level erasure needs: it is retiring the hashed value
        every such row carries, not editing any individual row's own history the append-only
        guard exists to protect. Named and centralized (rather than a bare `.filter(...).
        update(value_key="")` inline at the call site) so exactly one caller doing this can be
        proven by a test (grep-style: `ham.requests.services.purge_expired_request` is the
        only call site), instead of trusting that no other code ever reaches for the same
        queryset-level escape hatch for a different reason."""
        return self.filter(request=request).update(value_key="")


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

    objects = RequestContactVerificationManager()

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
