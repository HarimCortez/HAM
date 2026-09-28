"""Payload PII guard (PRD §68; foundation.md §3 "IDs and codes only, never S fields").

`ham.outbox.api.emit()` calls `validate_payload` before writing anything. It is intentionally
strict and heuristic rather than exhaustive: outbox payloads should only ever be ids, enum
codes, counts and similar — if a legitimate field name trips this, that is a sign the field
does not belong in an outbox payload, not a bug to work around.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from ham.platform.logging import EMAIL_RE, PHONE_RE

# Case-insensitive substring match against payload keys (recursively, at any nesting depth).
# Deliberately broad: a false positive just means the caller renames the field or resolves it
# in the subscriber's own service call instead of putting it in the payload.
_FORBIDDEN_KEY_PATTERN = re.compile(
    r"(email|phone|mobile|full[_-]?name|first[_-]?name|last[_-]?name|surname|"
    r"address|street|city|state|zip|postal|dob|birth|ssn|circumstance)",
    re.IGNORECASE,
)


class PayloadPIIError(ValueError):
    """Raised when an outbox payload contains a field that looks like PII (§68)."""


def validate_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise PayloadPIIError("outbox payload must be a dict")
    _walk(payload, path="payload")


def _walk(value: Any, *, path: str) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise PayloadPIIError(f"{path}: keys must be strings, got {type(key).__name__}")
            if _FORBIDDEN_KEY_PATTERN.search(key):
                raise PayloadPIIError(
                    f"{path}.{key} looks like a PII field name; outbox payloads may only carry "
                    "IDs and codes (PRD §68, foundation.md §3) — subscribers resolve details "
                    "through their own services instead"
                )
            _walk(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _walk(item, path=f"{path}[{index}]")
    elif isinstance(value, str):
        if _looks_like_uuid(value):
            return
        if EMAIL_RE.search(value) or PHONE_RE.search(value):
            raise PayloadPIIError(
                f"{path} value looks like an email address or phone number; outbox payloads "
                "may only carry IDs and codes (PRD §68)"
            )


def _looks_like_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return True
