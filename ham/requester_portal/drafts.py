"""Unfinished public-form storage (intake.md §3 `IntakeDraft`; Q-100, Q-127, Q-139, Q-121).

The whole answer set (including **P**/**C** fields) is kept only as a single Fernet-encrypted
blob (`ham.platform.crypto`) — never as individual plaintext columns — and erased 24 h after
creation whether or not it was ever verified (`ham.requester_portal.jobs.purge_expired_drafts`).
Nothing in this module ever hands a decrypted payload back across a service boundary meant for
a response (Q-139 "the resume prompt shows no details"); `load_payload` is for server-side use
by `save_step`/`ham.requester_portal.services.submit_and_issue_link` only.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from uuid import UUID

from django.db import transaction

from ham.platform import otp
from ham.platform.clock import now as clock_now
from ham.platform.crypto import decrypt, encrypt
from ham.rules import RULES

from .models import IntakeDraft, RequesterVerificationChallenge

_RATE_WINDOW = dt.timedelta(hours=1)


def _email_key(email: str | None) -> str:
    if not email:
        return ""
    return otp.hash_value(email.strip().lower())


@dataclass(frozen=True, slots=True)
class DraftStartResult:
    status: str  # "created" | "rate_limited"
    draft: IntakeDraft | None = None


def start_draft(*, ip_address: str = "", email: str | None = None) -> DraftStartResult:
    """Q-121: `INTAKE_FORMS_PER_IP_PER_HOUR` new drafts per IP per rolling hour. An empty
    ``ip_address`` (e.g. in a unit test) is never rate-limited — there is nothing to key on."""
    now = clock_now()
    if ip_address:
        window_start = now - _RATE_WINDOW
        recent = IntakeDraft.objects.filter(
            ip_address=ip_address, created_at__gte=window_start
        ).count()
        if recent >= RULES.intake.INTAKE_FORMS_PER_IP_PER_HOUR:
            return DraftStartResult("rate_limited")
    draft = IntakeDraft.objects.create(
        payload_ciphertext=encrypt(json.dumps({})),
        email_key=_email_key(email),
        ip_address=ip_address or None,
        created_at=now,
        expires_at=now + RULES.intake.INTAKE_DRAFT_LIFETIME,
    )
    return DraftStartResult("created", draft)


def _live(draft_id: UUID, *, now: dt.datetime, for_update: bool = False) -> IntakeDraft | None:
    qs = IntakeDraft.objects.select_for_update() if for_update else IntakeDraft.objects
    return qs.filter(pk=draft_id, consumed_at__isnull=True, expires_at__gt=now).first()


def load_payload(draft_id: UUID, *, now: dt.datetime | None = None) -> dict | None:
    """Server-side only (never returned by a public-facing view/API, Q-139). ``None`` for an
    unknown, consumed or expired draft."""
    draft = _live(draft_id, now=now or clock_now())
    if draft is None:
        return None
    return json.loads(decrypt(draft.payload_ciphertext))


def save_step(draft_id: UUID, step_data: dict, *, email: str | None = None) -> IntakeDraft | None:
    """Merge ``step_data`` into the draft's stored answers and save (intake.md §3 "saved at
    each step and survives errors"). Fixed ``expires_at`` (does not slide) — a form the person
    walked away from for good is still gone after `INTAKE_DRAFT_LIFETIME`.

    Returns ``None`` (nothing is written) for an unknown, consumed or expired draft id, so a
    caller with a stale/forged cookie value gets no information either way (no enumeration).
    """
    now = clock_now()
    with transaction.atomic():
        draft = _live(draft_id, now=now, for_update=True)
        if draft is None:
            return None
        payload = json.loads(decrypt(draft.payload_ciphertext))
        payload.update(step_data)
        draft.payload_ciphertext = encrypt(json.dumps(payload))
        update_fields = ["payload_ciphertext"]
        if email:
            new_key = _email_key(email)
            if new_key != draft.email_key:
                draft.email_key = new_key
                update_fields.append("email_key")
                # H1: a code already sent for the *old* email must not still work once the
                # draft's email has changed -- close the window even before
                # `submit_and_issue_link`'s own email_key check would catch a replay (e.g. if
                # the email were later edited back to the original value). Only unconsumed
                # challenges: one already redeemed (code/link used) keeps its own record of
                # what it verified; `submit_and_issue_link` checks that value against the
                # email actually being submitted, not against the draft's current value.
                RequesterVerificationChallenge.objects.filter(
                    draft_id=draft_id,
                    purpose=RequesterVerificationChallenge.PURPOSE_INTAKE,
                    consumed_at__isnull=True,
                ).update(expires_at=now - dt.timedelta(seconds=1))
        draft.save(update_fields=update_fields)
    return draft


def mark_consumed(draft_id: UUID, *, request_id: UUID) -> None:
    """Called once, inside the same transaction that creates the `AssistanceRequest`
    (`ham.requester_portal.services.submit_and_issue_link`) — a consumed draft is never
    resumable or re-submittable again."""
    IntakeDraft.objects.filter(pk=draft_id).update(consumed_at=clock_now(), request_id=request_id)


def consumed_request_id(draft_id: UUID) -> UUID | None:
    """M8: distinguishes "this draft's answers already became a real request" from "this
    draft id is simply unknown/expired" -- both look identical to `load_payload` (`None`
    either way). Used only to decide whether an already-used code/link should say "we
    already received your request" instead of a generic "please start again" error
    (`ham.web.views_requester`'s already-received handling)."""
    draft = IntakeDraft.objects.filter(pk=draft_id, consumed_at__isnull=False).first()
    return draft.request_id if draft is not None else None


def draft_exists_and_live(draft_id: UUID) -> bool:
    """For the resume flow: whether the cookie's draft id still resolves to something (never
    reveals *what*, Q-139)."""
    return _live(draft_id, now=clock_now()) is not None
