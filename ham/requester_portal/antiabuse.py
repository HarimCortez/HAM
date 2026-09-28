"""No third-party trackers or CAPTCHAs (intake.md §9, Q-121, CLAUDE.md §3.4).

Two client-side checks that fail *silently* (the caller always shows the same "Check your
email" success page and sends no email either way, so a bot learns nothing): a honeypot field
and a signed minimum-fill-time token. Rate limits themselves live next to what they count
(`ham.requester_portal.drafts`/`.verification`) since each needs its own model to query.
"""

from __future__ import annotations

import datetime as dt

from ham.platform import otp
from ham.platform.clock import now as clock_now
from ham.rules import RULES

# A decoy field name a real person never sees or fills in (rendered off-screen by the
# template, S2.7); any non-empty value here means a bot filled every field it could find.
HONEYPOT_FIELD_NAME = "organization_website"


def honeypot_tripped(value: str | None) -> bool:
    return bool(value)


def sign_form_opened_at(*, now: dt.datetime | None = None) -> str:
    """Embed this in a hidden field when the form page is first rendered (GET). Not itself a
    secret — signed only so a bot can't forge an *older* timestamp to skip the fill-time
    check; `ham.platform.otp` reuses the same reviewed HMAC construction as sign-in codes."""
    ts = (now or clock_now()).isoformat()
    return f"{ts}|{otp.hash_value(ts)}"


def min_fill_time_ok(token: str | None, *, now: dt.datetime | None = None) -> bool:
    """True once `RULES.intake.INTAKE_MIN_FILL_TIME` has elapsed since a genuine
    ``sign_form_opened_at`` token. Missing, malformed or tampered tokens fail closed."""
    if not token or "|" not in token:
        return False
    ts_text, _, sig = token.partition("|")
    if not otp.hash_matches(ts_text, sig):
        return False
    try:
        opened_at = dt.datetime.fromisoformat(ts_text)
    except ValueError:
        return False
    return (now or clock_now()) - opened_at >= RULES.intake.INTAKE_MIN_FILL_TIME


__all__ = ["HONEYPOT_FIELD_NAME", "honeypot_tripped", "min_fill_time_ok", "sign_form_opened_at"]
