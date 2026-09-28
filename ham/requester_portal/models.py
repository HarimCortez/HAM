"""`ham.requester_portal`'s own tables (intake.md §3): `IntakeDraft`,
`RequesterVerificationChallenge`, `RequesterAccessLink`, `IntakeSource`.

``request_id``/``draft_id``/``verification_id`` fields here are plain ``UUIDField``s, never
``ForeignKey``s: ``ham.requests.AssistanceRequest`` is a sibling app built in parallel (S2.2,
its own worktree/branch) and this slice must not take a hard migration-graph dependency on
models that don't exist in this checkout. ``ham.requester_portal`` sits *above* ``ham.requests``
in the import-layer order (``ham.web -> ham.requester_portal -> ham.media -> ham.requests ->
...``), so once merged a later slice may tighten these to real FKs if desired; nothing here
relies on that.
"""

from __future__ import annotations

from django.db import models

from ham.platform.ids import UUID7Field


class IntakeDraft(models.Model):
    """PRD §6, Q-100, Q-127, Q-139: the whole unfinished public-form answer set, Fernet-
    encrypted end to end (``ham.platform.crypto``) so a database dump never carries plaintext
    requester PII/circumstances for a request that was never even verified. Erased 24 h after
    creation (``ham.requester_portal.jobs.purge_expired_drafts``) whether or not it was ever
    consumed into a request.
    """

    id = UUID7Field()
    payload_ciphertext = models.TextField()
    # **S**: HMAC of the normalized email typed so far (may be blank before that step), used
    # only for the per-email abuse-limit counters (Q-121) — never the raw address.
    email_key = models.CharField(max_length=64, blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)  # **S**
    created_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    request_id = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "requester_portal_draft"
        indexes = [
            models.Index(fields=["expires_at"], name="rp_draft_expires_idx"),
            models.Index(fields=["email_key", "created_at"], name="rp_draft_email_idx"),
            models.Index(fields=["ip_address", "created_at"], name="rp_draft_ip_idx"),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial; never logged (payload is **P**/**C**)
        return f"IntakeDraft({self.id})"


class RequesterVerificationChallenge(models.Model):
    """One emailed code+link for a requester (PRD §7.1; same shape/rules as
    ``ham.identity.models.SignInChallenge``, reusing ``RULES.intake.REQUESTER_CODE_*``).
    Exactly one of ``draft_id`` (``purpose="intake"``) / ``request_id``
    (``purpose="link_regeneration"``) is set."""

    PURPOSE_INTAKE = "intake"
    PURPOSE_LINK_REGENERATION = "link_regeneration"
    PURPOSE_CHOICES = [
        (PURPOSE_INTAKE, "Intake"),
        (PURPOSE_LINK_REGENERATION, "Link regeneration"),
    ]

    id = UUID7Field()
    purpose = models.CharField(max_length=32, choices=PURPOSE_CHOICES)
    draft_id = models.UUIDField(null=True, blank=True)
    request_id = models.UUIDField(null=True, blank=True)
    email_key = models.CharField(max_length=64)  # **S**
    code_hash = models.CharField(max_length=64)
    link_token_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    consumed_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)  # **S**

    class Meta:
        db_table = "requester_portal_challenge"
        indexes = [
            models.Index(fields=["email_key", "created_at"], name="rp_challenge_email_idx"),
            models.Index(fields=["ip_address", "created_at"], name="rp_challenge_ip_idx"),
            models.Index(fields=["expires_at"], name="rp_challenge_expires_idx"),
            models.Index(fields=["draft_id"], name="rp_challenge_draft_idx"),
            models.Index(fields=["request_id"], name="rp_challenge_request_idx"),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"RequesterVerificationChallenge({self.id}, {self.purpose})"


class RequesterAccessLink(models.Model):
    """One requester secure-page access token (intake.md §3, §4, §7.3; Q-102, Q-116, Q-117).

    Lookup is always by ``token_hash`` (HMAC, ``ham.platform.otp``); ``token_ciphertext``
    (Fernet, ``ham.platform.crypto``) exists solely so a later "every requester email carries
    the link" (Q-102) send can re-derive the raw token without ever storing it in the clear.
    """

    KIND_INITIAL = "initial"
    KIND_REGENERATED = "regenerated"
    KIND_CHOICES = [(KIND_INITIAL, "Initial"), (KIND_REGENERATED, "Regenerated")]

    REVOKE_SUPERSEDED = "superseded"
    REVOKE_ANONYMIZED = "anonymized"
    REVOKE_CHOICES = [(REVOKE_SUPERSEDED, "Superseded"), (REVOKE_ANONYMIZED, "Anonymized")]

    id = UUID7Field()
    request_id = models.UUIDField()
    token_hash = models.CharField(max_length=64, unique=True)
    token_ciphertext = models.TextField()
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    issued_at = models.DateTimeField()
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoke_reason = models.CharField(max_length=16, choices=REVOKE_CHOICES, blank=True, default="")
    verification_id = models.UUIDField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "requester_portal_link"
        constraints = [
            models.UniqueConstraint(
                fields=["request_id"],
                condition=models.Q(revoked_at__isnull=True),
                name="rp_link_one_live_per_request",
            )
        ]
        indexes = [models.Index(fields=["request_id"], name="rp_link_request_idx")]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"RequesterAccessLink({self.id}, {self.kind})"


class IntakeSource(models.Model):
    """Church-issued source codes recording where a public-form visitor came from (Q-114:
    "Same form with an optional short code (link/QR) recording the source; grants nothing
    extra; Director/AD create and deactivate codes.").

    This slice (S2.3) implements the model plus a read-only code -> label lookup for the
    public form only, per its brief ("model and lookup only; the management screen comes
    later"). The `intake_source.manage` matrix action (create/deactivate, Director/AD) is
    `ham.requests`' to wire up in a later slice.

    Merge note: intake.md §3 places `IntakeSource` under `ham.requests`
    (`requests_intake_source`) since that app's slice (S2.2, running in parallel in a
    different worktree) owns request-side leadership screens generally. Defined here instead
    to avoid a cross-worktree model collision in this slice; the merge should keep exactly one
    `IntakeSource` model (whichever app the orchestrator prefers) and repoint the other side's
    references — see this slice's handback.
    """

    id = UUID7Field()
    code = models.CharField(max_length=6, unique=True)
    label = models.CharField(max_length=120)
    created_by_user_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField()
    deactivated_at = models.DateTimeField(null=True, blank=True)
    deactivated_by_user_id = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "requester_portal_intake_source"

    def __str__(self) -> str:  # pragma: no cover - trivial; label carries no PII
        return f"IntakeSource({self.code})"
