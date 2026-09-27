"""Canonical serialization and content hash of a rule set.

The hash covers every group, every rule name, every value and its type. It does NOT cover
labels, notes or sources, so wording can be improved without a version bump. Changing any
value (or adding/removing/renaming a rule) changes the hash.
"""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any

from .types import CalendarYears, Pending
from .v1 import Rules, iter_rules


def encode_value(value: object) -> Any:
    """JSON-safe, type-tagged, deterministic encoding of one rule value."""
    if isinstance(value, Pending):
        return {"pending": value.question}
    if isinstance(value, bool):  # before int: bool is an int subclass
        return {"bool": value}
    if isinstance(value, int):
        return {"int": value}
    if isinstance(value, str):
        return {"str": value}
    if isinstance(value, timedelta):
        return {
            "timedelta_us": (value.days * 86_400 + value.seconds) * 1_000_000 + value.microseconds
        }
    if isinstance(value, CalendarYears):
        return {"calendar_years": value.years}
    if isinstance(value, tuple):
        return {"tuple": [encode_value(v) for v in value]}
    raise TypeError(f"Unsupported rule value type: {type(value).__name__}")


def canonical_document(rules: Rules) -> dict[str, dict[str, Any]]:
    doc: dict[str, dict[str, Any]] = {}
    for gf, rf, value in iter_rules(rules):
        doc.setdefault(gf.name, {})[rf.name] = encode_value(value)
    return doc


def content_hash(rules: Rules) -> str:
    """``sha256:<hex>`` of the canonical JSON of all rule values."""
    blob = json.dumps(
        canonical_document(rules), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return "sha256:" + hashlib.sha256(blob).hexdigest()
