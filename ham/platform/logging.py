"""Structured logging that never contains PII (PRD §68, CLAUDE.md "Never log ... sensitive
fields"): no requester name/address/contact, no volunteer email or phone, anywhere in a log
line, even inside an exception message.

Every handler in `LOGGING` (config/settings/base.py) has `ScrubPIIFilter` attached, so a
message gets scrubbed even if the calling code forgot to. Callers should still log an id
(`user_id=...`), never a name or email, in the first place — the scrubber is a safety net,
not a license to log freely.
"""

from __future__ import annotations

import json
import logging
import re
import traceback

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# Loosely-formatted phone numbers: 7+ digits, optionally grouped with +, -, ., spaces, parens.
PHONE_RE = re.compile(r"(?<!\w)(\+?\d[\d\-.\s()]{6,}\d)(?!\w)")
REDACTED = "[REDACTED]"


def scrub(text: str) -> str:
    """Replace anything that looks like an email address or a phone number."""
    if not isinstance(text, str):
        return text
    text = EMAIL_RE.sub(REDACTED, text)
    text = PHONE_RE.sub(REDACTED, text)
    return text


class ScrubPIIFilter(logging.Filter):
    """Rewrites `record.msg`/`record.args` and any exception text to their scrubbed form
    before a record reaches its handler's formatter."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = scrub(record.getMessage())
            record.args = ()
            if record.exc_info:
                record.exc_text = scrub(
                    record.exc_text or "".join(traceback.format_exception(*record.exc_info))
                )
        except Exception:
            # A scrubbing bug must never crash logging or leak the unscrubbed message.
            record.msg = "[unscrubbable log message suppressed]"
            record.args = ()
            record.exc_text = None
        return True


_STANDARD_RECORD_KEYS = frozenset(logging.makeLogRecord({}).__dict__.keys())

# Security review C2: some third-party loggers (notably Procrastinate's own "Starting job
# ...(to=..., text_body=...)" INFO line) attach a whole job description — including its task
# *args* — as a single nested `extra` value (e.g. `record.job = {"task_kwargs": {...}, ...}`).
# `ScrubPIIFilter` only rewrites `record.msg`, so that nested structure reached the JSON output
# untouched. Drop it outright (its content is either the already-encrypted payload
# `ham.integrations.email.service` now enqueues, or genuinely internal job bookkeeping no log
# reader needs) rather than trying to guess which nested keys are safe.
_DROPPED_EXTRA_KEYS = frozenset({"job"})


def _scrub_value(value: object) -> object:
    """Recursively scrub strings inside dict/list/tuple `extra` values (C2): the flat
    `scrub()` above only ever saw `record.msg`, not a structured value attached as an extra."""
    if isinstance(value, str):
        return scrub(value)
    if isinstance(value, dict):
        return {k: _scrub_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub_value(v) for v in value]
    return value


class JSONFormatter(logging.Formatter):
    """One JSON object per line: easy to grep and to feed to a log aggregator, and it makes
    "no free-text PII sneaking in via string interpolation" easier to audit than a printf
    format ever would."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
        }
        if record.exc_info:
            payload["exc_info"] = record.exc_text or self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if (
                key in _STANDARD_RECORD_KEYS
                or key in payload
                or key.startswith("_")
                or key in _DROPPED_EXTRA_KEYS
            ):
                continue
            try:
                json.dumps(value, default=str)
            except TypeError:
                continue
            payload[key] = _scrub_value(value)
        return json.dumps(payload, default=str)
