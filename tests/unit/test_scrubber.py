from __future__ import annotations

import logging

from ham.platform.logging import ScrubPIIFilter, scrub


def test_scrub_redacts_email():
    assert scrub("contact kevin.t@example.org now") == "contact [REDACTED] now"


def test_scrub_redacts_phone_number():
    assert scrub("call +1 (305) 555-0134 today") == "call [REDACTED] today"
    assert scrub("call 305-555-0134 today") == "call [REDACTED] today"


def test_scrub_leaves_ordinary_text_alone():
    assert scrub("user_id=1234 disabled account") == "user_id=1234 disabled account"


def test_scrub_ignores_non_string_input():
    assert scrub(42) == 42


def test_filter_scrubs_formatted_message_and_args():
    record = logging.LogRecord(
        name="ham",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="user %s emailed %s",
        args=("kevin", "kevin.t@example.org"),
        exc_info=None,
    )
    ScrubPIIFilter().filter(record)
    assert "example.org" not in record.getMessage()
    assert record.args == ()


def test_filter_never_raises_even_on_bad_input():
    record = logging.LogRecord(
        name="ham",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="%s",
        args=(object(),),
        exc_info=None,
    )
    assert ScrubPIIFilter().filter(record) is True
