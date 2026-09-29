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


class UrgencyReason(models.TextChoices):
    """docs/ux/intake.md R2 "Why is it urgent?" chips. UX M4/N-M1: the ONE vocabulary for
    urgency reason (same "one canonical, lower-layer vocabulary" pattern as `NeedCategory`/
    `PropertyType` above) -- `ham.requester_portal.choices.UrgencyReason` re-exports this
    rather than defining its own, differently-coded copy. Stored as its own field
    (`AssistanceRequest.urgency_reason`), always separate from the requester's own free-text
    `urgency_justification` -- the two must never be concatenated into one stored string
    (that was the bug: re-saving the draft kept re-prefixing the label onto the text)."""

    SOMEONE_COULD_GET_HURT = "someone_could_get_hurt", "Someone could get hurt"
    WATER_OR_DAMAGE = "water_or_damage", "Water is coming in or damage is getting worse"
    NO_UTILITIES = "no_utilities", "No power, water, heat or cooling"
    CANT_GET_IN_OR_OUT = "cant_get_in_or_out", "Can't get in or out of the home safely"
    SOMETHING_ELSE = "something_else", "Something else"


class RequestSource(models.TextChoices):
    PUBLIC_FORM = "public_form", "Public form"
    CHURCH_LINK = "church_link", "Church-issued link"
    ASSISTED = "assisted", "Entered on someone's behalf"


# ------------------------------------------------------------------------------------------
# Step 3 (approvals) vocabularies -- approvals.md §2.1, docs/prd-open-questions.md Q-154,
# Q-157, Q-159, Q-163, Q-164, Q-174. One vocabulary each, same "no second, differently-coded
# copy" convention as NeedCategory/PropertyType above.
# ------------------------------------------------------------------------------------------
class ApprovalStage(models.TextChoices):
    INITIAL = "initial", "Initial decision"
    RECONSIDERATION = "reconsideration", "Reconsideration decision"


class ApprovalOutcome(models.TextChoices):
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class ApprovalRoute(models.TextChoices):
    """Q-164: chosen at decision time by whoever is deciding (defaulting to pastoral in the
    UI only -- nothing is preselected in the stored data); never inferred from role alone."""

    PASTORAL = "pastoral", "Pastoral"
    BOARD = "board", "Board"


class RejectionReason(models.TextChoices):
    """Q-154 (decided): the five reason codes a rejection (or a "keep the rejection" final
    reconsideration decision) must carry. Grounded in §5; "outside the area" and "needs a
    licensed professional" were dropped by the owner reconciliation. Kept forever on the
    decision record (reports, the §9 duplicate panel) even though the accompanying kind
    message is erased at the 7-year purge (Q-145)."""

    FAMILY_OR_OTHERS_CAN_HELP = (
        "family_or_others_can_help",
        "Family or others may be able to help",
    )
    OWNER_OR_LANDLORD_RESPONSIBLE = (
        "owner_or_landlord_responsible",
        "The owner or landlord is responsible for this repair",
    )
    NOT_HELP_HAM_OFFERS = "not_help_ham_offers", "This isn't the kind of help HAM offers"
    COULDNT_CONFIRM = "couldnt_confirm", "We couldn't confirm what we needed"
    ANOTHER_REASON = "another_reason", "Another reason"


class RequesterChannel(models.TextChoices):
    """How a requester-facing fact was captured: on the secure page themselves, or recorded
    by staff from a phone call (Q-159, no-email requesters). Shared by
    `Reconsideration.requested_via` and `RequestQuestion.answered_via` -- one vocabulary, not
    two differently-coded copies (see `NeedCategory`'s docstring above for why)."""

    SECURE_PAGE = "secure_page", "Secure page"
    PHONE = "phone", "Phone"


class QuestionCloseReason(models.TextChoices):
    WITHDRAWN = "withdrawn", "Withdrawn"
    REQUEST_CLOSED = "request_closed", "Request closed"


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
    # UX M4/N-M1: the chosen reason *code* -- never prefixed onto `urgency_justification`
    # (the requester's own words). A code, not free text, so it is kept (not blanked) at the
    # 7-year retention purge, unlike `urgency_justification` (Q-145).
    urgency_reason = models.CharField(
        max_length=32, choices=UrgencyReason.choices, blank=True, default=""
    )
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

    # Step 3 (approvals.md §2.1, §10): set by CERTIFY_URGENCY / DECLINE_URGENCY.
    urgency_reviewed_at = models.DateTimeField(null=True, blank=True)
    urgency_reviewed_by_user_id = models.UUIDField(null=True, blank=True)
    # Q-155/Q-174: set once, on the first REJECT, to decided_at's church-local day end +
    # RECONSIDERATION_REQUEST_WINDOW (S3.1 rule), stored in UTC so the date printed in the
    # rejection email never shifts later even if the rule changes (D3's reasoning). Null until
    # the request is first rejected; unused for an approved/still-open request.
    reconsideration_deadline_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "requests_request"
        indexes = [
            models.Index(
                fields=["status", "urgent_requested", "submitted_at"], name="req_status_urg_idx"
            ),
        ]
        constraints = [
            # UX M4/N-M1: justification is required when urgent only for the "Something
            # else" reason (every other reason chip is self-explanatory) -- not urgent =>
            # always empty; urgent + "something_else" => never empty; any other urgent
            # reason => either is fine.
            models.CheckConstraint(
                condition=(
                    models.Q(urgent_requested=False, urgency_justification="")
                    | models.Q(urgent_requested=True)
                    & (
                        ~models.Q(urgency_reason=UrgencyReason.SOMETHING_ELSE.value)
                        | ~models.Q(urgency_justification="")
                    )
                ),
                name="req_urgency_justification_iff_urgent",
            ),
            # UX M4/N-M1: a reason code is required whenever urgent is ticked, same shape as
            # the justification constraint above -- catches any future write path (not just
            # the public form) that forgets to set it.
            models.CheckConstraint(
                condition=(
                    models.Q(urgent_requested=False, urgency_reason="")
                    | models.Q(urgent_requested=True) & ~models.Q(urgency_reason="")
                ),
                name="req_urgency_reason_iff_urgent",
            ),
            # Step-3 bug fix (approvals.md §2.1 "Fix a constraint bug"): the old
            # `req_closed_at_when_terminal` was a tautology --
            # `closed_at IS NULL OR status <> CANCELLED OR closed_at IS NOT NULL` is always
            # true (the first and third arms alone cover every row) and never actually
            # constrained anything. Replaced with two real CHECKs: CANCELLED always carries a
            # `closed_at`; every status that is never closed (NEEDS_PHONE_CHECK, SUBMITTED,
            # AWAITING_APPROVAL, RECONSIDERATION_PENDING, APPROVED) never does. REJECTED is the
            # only status allowed either way (Q-116: still-reconsiderable vs. final, §2.1).
            models.CheckConstraint(
                condition=(
                    ~models.Q(status=RequestStatus.CANCELLED.value)
                    | models.Q(closed_at__isnull=False)
                ),
                name="req_closed_at_set_when_cancelled",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(
                        status__in=[
                            RequestStatus.NEEDS_PHONE_CHECK.value,
                            RequestStatus.SUBMITTED.value,
                            RequestStatus.AWAITING_APPROVAL.value,
                            RequestStatus.RECONSIDERATION_PENDING.value,
                            RequestStatus.APPROVED.value,
                        ]
                    )
                    | models.Q(closed_at__isnull=True)
                ),
                name="req_closed_at_null_while_open",
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


class AppendOnlyOnceMixin:
    """Step 3 (approvals.md §2.1): insert-only, except a fixed set of fields (``ONCE_FIELDS``)
    each settable exactly once, from an empty/falsy default, generalizing
    `RequestContactVerification`'s single-field append-only guard above to models with more
    than one such exception (`Approval.requester_phoned_at`/`.undone_at`/`.effects_ran_at`,
    `RequestQuestion.answer`/`.closed_at`). A model with no exceptions at all
    (`Reconsideration`) simply leaves ``ONCE_FIELDS`` empty -- every update then raises,
    i.e. fully immutable after insert, matching architecture/approvals.md §2.1's "immutable
    after insert" for that model.

    Callers updating a once-field **must** pass ``update_fields=[...]`` naming only
    once-fields (mirrors Django's own convention that `update_fields` is the "I mean exactly
    these columns" signal); this is a Python-level guard, same as `AppendOnlyError`'s own
    docstring explains for why there is no DB trigger here.
    """

    ONCE_FIELDS: frozenset[str] = frozenset()

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self._state.adding:  # type: ignore[attr-defined]
            super().save(*args, **kwargs)  # type: ignore[misc]
            return
        update_fields = kwargs.get("update_fields")
        touched = frozenset(update_fields) if update_fields is not None else frozenset()
        if not touched or not touched <= self.ONCE_FIELDS:
            raise AppendOnlyError(
                f"{type(self).__name__} is append-only; create a new row instead of updating "
                f"one, or update only {sorted(self.ONCE_FIELDS)} (once each, via "
                "update_fields=[...])."
            )
        current = type(self).objects.filter(pk=self.pk).values(*touched).first()  # type: ignore[attr-defined]
        if current is None:
            raise AppendOnlyError(f"{type(self).__name__}({self.pk}) does not exist.")  # type: ignore[attr-defined]
        for field_name in touched:
            if current[field_name] not in (None, "", False):
                raise AppendOnlyError(
                    f"{type(self).__name__}.{field_name} is already set; it may be set "
                    "exactly once."
                )
        super().save(*args, **kwargs)  # type: ignore[misc]

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise AppendOnlyError(f"{type(self).__name__} rows are never deleted.")


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


# ============================================================================================
# Step 3 (approvals): Approval, Reconsideration, RequestQuestion (approvals.md §2.1, §66;
# approvals-contracts.md §1). One migration together with the AssistanceRequest additions
# above and the two fixed CHECKs (S3.0), so S3.1-S3.7 never collide on a `requests` migration.
# ============================================================================================
class ApprovalManager(models.Manager):
    """Q-127/Q-145 retention seam (mirrors `RequestContactVerificationManager` above): the
    named, centralized exception to "append-only" for a genuine system-level 7-year erasure.
    Not yet called from `ham.requests.services.purge_expired_request` (S3.2 owns that write
    path) -- declared here so the schema and the one legal call site are both fixed by S3.0,
    and S3.2 only has to wire the call, not invent the bypass."""

    def erase_text_for_retention(self, request: AssistanceRequest) -> int:
        """Blanks every `Approval.reason`/`.approval_note` for ``request`` (Q-145). Codes
        (`reason_code`, `outcome`, `route`), dates and ids are kept -- outcome reporting
        depends on them surviving the purge."""
        return self.filter(request=request).update(reason="", approval_note="")


class Approval(AppendOnlyOnceMixin, models.Model):
    """The decision record (§66; approvals.md §2.1). One row per `(request, stage)` --
    `UNIQUE` below enforces "one first decision, at most one reconsideration decision"
    (§8.2, §8.4, D1/Q-153). Append-only except `ONCE_FIELDS` (the told-by-phone pair, the
    undo pair, and the held-effects idempotency marker), each settable once from null.

    Q-156/Q-176 (undo): a decision is "pending" from `decided_at` until `effective_at`
    (`= decided_at + RULES.approvals.DECISION_UNDO_WINDOW`, computed and stored at write time
    -- never recomputed from the live rule, so a later rules change never moves an existing
    decision's own window, D3's "store the date, don't recompute it" reasoning reused). The
    held effects (requester email, media batch close, question withdrawal, the "decision"
    in-app update to other leaders) run once, at `effective_at`, unless `undone_at` is set by
    then -- see `docs/architecture/approvals-contracts.md` §4 "Held effects" for the exact
    job design and why the urgent-approval alert is deliberately NOT one of the held effects.
    """

    id = UUID7Field()
    request = models.ForeignKey(
        AssistanceRequest, on_delete=models.CASCADE, related_name="approvals"
    )
    stage = models.CharField(max_length=16, choices=ApprovalStage.choices)
    outcome = models.CharField(max_length=16, choices=ApprovalOutcome.choices)
    route = models.CharField(max_length=16, choices=ApprovalRoute.choices)  # Q-164
    decided_by_user_id = models.UUIDField()
    decided_at = models.DateTimeField()
    # Q-156/Q-176: see the class docstring. Held effects run here unless undone first.
    effective_at = models.DateTimeField()
    board_decided_on = models.DateField(null=True, blank=True)  # Q-163: Board route only
    reason_code = models.CharField(
        max_length=32, choices=RejectionReason.choices, blank=True, default=""
    )
    reason = models.TextField(blank=True, default="")  # C: rejection message / recon. reason
    # Q-169: optional one-line "Why approved (leaders only)" note, approval only.
    approval_note = models.TextField(blank=True, default="")  # C
    urgent_approval = models.BooleanField(default=False)
    took_over_from_user_id = models.UUIDField(null=True, blank=True)  # Q-157
    # Q-157: the required tick "Pastor X isn't available to decide this" -- set once, at
    # insert, together with `took_over_from_user_id` (never one without the other, see the
    # CHECK constraint below); NOT a `ONCE_FIELDS` entry (it is never set *after* insert).
    unavailable_confirmed = models.BooleanField(default=False)
    # Q-159 ("I've already told them by phone", no-email requests): ONCE_FIELDS, set once
    # together, from null.
    requester_phoned_at = models.DateTimeField(null=True, blank=True)
    requester_phoned_by_user_id = models.UUIDField(null=True, blank=True)
    # Q-156/Q-176: ONCE_FIELDS, set once together, from null. The record is kept, never
    # deleted, and marked undone -- never resets the other fields above.
    undone_at = models.DateTimeField(null=True, blank=True)
    undone_by_user_id = models.UUIDField(null=True, blank=True)
    # Idempotency marker for the held-effects job (contracts.md §4): set once the job has run
    # the held effects for this decision, so a retried/duplicate job invocation is a no-op.
    # Not itself an audited fact -- no *_by_user_id (SYSTEM sets it).
    effects_ran_at = models.DateTimeField(null=True, blank=True)

    ONCE_FIELDS = frozenset(
        {
            "requester_phoned_at",
            "requester_phoned_by_user_id",
            "undone_at",
            "undone_by_user_id",
            "effects_ran_at",
        }
    )

    objects = ApprovalManager()

    class Meta:
        db_table = "requests_approval"
        indexes = [models.Index(fields=["request", "decided_at"], name="approval_request_idx")]
        constraints = [
            # Q-156/Q-176 (undo is a real "fix a mistake", not just a marker): only *live*
            # (not-undone) decisions are unique per (request, stage) -- an undone decision
            # frees its stage for a fresh one, by the same or a different eligible approver.
            # A plain `UNIQUE(request, stage)` would wrongly keep blocking that second
            # decision forever once one row for the stage had ever been undone.
            # Q-156/Q-176 (undo is a real "fix a mistake", not just a marker): only *live*
            # (not-undone) decisions are unique per (request, stage) -- an undone decision
            # frees its stage for a fresh one, by the same or a different eligible approver.
            # A plain `UNIQUE(request, stage)` would wrongly keep blocking that second
            # decision forever once one row for the stage had ever been undone.
            models.UniqueConstraint(
                fields=["request", "stage"],
                condition=models.Q(undone_at__isnull=True),
                name="approval_unique_live_stage",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(outcome=ApprovalOutcome.REJECTED.value)
                    | (~models.Q(reason_code="") & ~models.Q(reason=""))
                ),
                name="approval_reason_required_when_rejected",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(stage=ApprovalStage.RECONSIDERATION.value) | ~models.Q(reason="")
                ),
                name="approval_reason_required_at_reconsideration",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(urgent_approval=True)
                    | models.Q(outcome=ApprovalOutcome.APPROVED.value)
                ),
                name="approval_urgent_only_when_approved",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(route=ApprovalRoute.BOARD.value)
                    | models.Q(board_decided_on__isnull=False)
                ),
                name="approval_board_decided_on_required_for_board_route",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(took_over_from_user_id__isnull=True)
                    | models.Q(unavailable_confirmed=True)
                ),
                name="approval_takeover_requires_unavailable_confirmed",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(undone_at__isnull=True, undone_by_user_id__isnull=True)
                    | models.Q(undone_at__isnull=False, undone_by_user_id__isnull=False)
                ),
                name="approval_undone_fields_set_together",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        requester_phoned_at__isnull=True, requester_phoned_by_user_id__isnull=True
                    )
                    | models.Q(
                        requester_phoned_at__isnull=False,
                        requester_phoned_by_user_id__isnull=False,
                    )
                ),
                name="approval_phoned_fields_set_together",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"Approval({self.request_id}, {self.stage}, {self.outcome})"


class ReconsiderationManager(models.Manager):
    """Retention seam, see `ApprovalManager`'s own docstring."""

    def erase_text_for_retention(self, request: AssistanceRequest) -> int:
        """Blanks `Reconsideration.requester_note` for ``request`` (Q-145)."""
        return self.filter(request=request).update(requester_note="")


class Reconsideration(AppendOnlyOnceMixin, models.Model):
    """The one reconsideration request a rejected request may ever carry (§66, §8.4).
    Immutable after insert (`ONCE_FIELDS` empty) -- its *decision* is a separate `Approval`
    row (`stage=reconsideration`), derived by `(request_id, stage)`, never linked by FK, so
    both rows stay independently immutable (approvals.md §2.1)."""

    id = UUID7Field()
    request = models.OneToOneField(
        AssistanceRequest, on_delete=models.CASCADE, related_name="reconsideration"
    )
    requested_at = models.DateTimeField()
    requested_via = models.CharField(max_length=16, choices=RequesterChannel.choices)
    recorded_by_user_id = models.UUIDField(null=True, blank=True)  # phone only, Q-159
    requester_note = models.TextField(blank=True, default="")  # C, Q-158, <=1000 chars
    route = models.CharField(max_length=16, choices=ApprovalRoute.choices)  # from the rejection
    original_decider_user_id = models.UUIDField()

    objects = ReconsiderationManager()

    class Meta:
        db_table = "requests_reconsideration"
        constraints = [
            models.CheckConstraint(
                condition=(
                    ~models.Q(requested_via=RequesterChannel.PHONE.value)
                    | models.Q(recorded_by_user_id__isnull=False)
                ),
                name="reconsideration_phone_requires_recorder",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"Reconsideration({self.request_id})"


class RequestQuestionManager(models.Manager):
    """Retention seam, see `ApprovalManager`'s own docstring."""

    def erase_text_for_retention(self, request: AssistanceRequest) -> int:
        """Blanks every `RequestQuestion.question`/`.answer` for ``request`` (Q-145)."""
        return self.filter(request=request).update(question="", answer="")


class RequestQuestion(AppendOnlyOnceMixin, models.Model):
    """A HAM question to the requester and its answer (§7.2, §66). The question text is
    never edited (not a `ONCE_FIELDS` entry); the answer, once recorded, is set exactly once
    (`ONCE_FIELDS`) -- one answer per question, §7.2. Status is derived, not stored: open (no
    answer, not closed) / answered / closed (see `ham.requests.queries`, S3.3)."""

    id = UUID7Field()
    request = models.ForeignKey(
        AssistanceRequest, on_delete=models.CASCADE, related_name="questions"
    )
    asked_by_user_id = models.UUIDField()
    asked_at = models.DateTimeField()
    question = models.TextField()  # C, <=500 chars (form-level), immutable

    answer = models.TextField(blank=True, default="")  # C, <=2000 chars (form-level)
    answered_at = models.DateTimeField(null=True, blank=True)
    answered_via = models.CharField(
        max_length=16, choices=RequesterChannel.choices, blank=True, default=""
    )
    answer_recorded_by_user_id = models.UUIDField(null=True, blank=True)  # phone only

    closed_at = models.DateTimeField(null=True, blank=True)
    close_reason = models.CharField(
        max_length=16, choices=QuestionCloseReason.choices, blank=True, default=""
    )
    closed_by_user_id = models.UUIDField(null=True, blank=True)

    ONCE_FIELDS = frozenset(
        {
            "answer",
            "answered_at",
            "answered_via",
            "answer_recorded_by_user_id",
            "closed_at",
            "close_reason",
            "closed_by_user_id",
        }
    )

    objects = RequestQuestionManager()

    class Meta:
        db_table = "requests_question"
        indexes = [
            # Drives the "Waiting on requester" view (approvals.md §2.1).
            models.Index(
                fields=["request"],
                condition=models.Q(answered_at__isnull=True, closed_at__isnull=True),
                name="reqq_open_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(answer="", answered_at__isnull=True)
                    | (~models.Q(answer="") & models.Q(answered_at__isnull=False))
                ),
                name="reqq_answer_iff_answered_at",
            ),
            models.CheckConstraint(
                condition=~(
                    models.Q(answered_at__isnull=False) & models.Q(closed_at__isnull=False)
                ),
                name="reqq_not_answered_and_closed",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"RequestQuestion({self.request_id})"
