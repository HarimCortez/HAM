"""Q-139: the "resume my request" handle. "Resume only in the same browser; the prompt shows
no details; draft erased after 24 h."

Implemented as a signed, ``httponly`` cookie holding only the draft id (Django's
``django.core.signing``, keyed off ``SECRET_KEY`` — same trust boundary as the session cookie).
A cookie is inherently browser-scoped (never sent cross-origin, never in a URL a person could
forward), which is what makes "same browser only" true here without any extra device-binding
logic. The cookie carries no requester content at all — resuming means the view loads the
*draft id* from the cookie and continues collecting answers into that same
(still-encrypted, still never redisplayed) draft; it is never decrypted and echoed back into a
response (Q-139 "the prompt shows no details").
"""

from __future__ import annotations

from uuid import UUID

from django.core import signing
from django.http import HttpRequest, HttpResponse

from ham.rules import RULES

COOKIE_NAME = "ham_intake_draft"
_SALT = "ham.requester_portal.draft_resume"


def set_resume_cookie(response: HttpResponse, *, draft_id: UUID) -> None:
    max_age = int(RULES.intake.INTAKE_DRAFT_LIFETIME.total_seconds())
    response.set_cookie(
        COOKIE_NAME,
        signing.dumps(str(draft_id), salt=_SALT),
        max_age=max_age,
        httponly=True,
        samesite="Lax",
        secure=True,
    )


def clear_resume_cookie(response: HttpResponse) -> None:
    response.delete_cookie(COOKIE_NAME)


def read_resume_draft_id(request: HttpRequest) -> UUID | None:
    """The draft id the *same browser* has an unfinished form for, or ``None`` if there is no
    cookie, it doesn't verify, or it's older than the draft lifetime (mirrors the draft's own
    ``expires_at``, so a stale cookie never resolves to nothing useful)."""
    raw = request.COOKIES.get(COOKIE_NAME)
    if not raw:
        return None
    max_age = int(RULES.intake.INTAKE_DRAFT_LIFETIME.total_seconds())
    try:
        value = signing.loads(raw, salt=_SALT, max_age=max_age)
    except signing.BadSignature:
        return None
    try:
        return UUID(value)
    except (TypeError, ValueError):
        return None
