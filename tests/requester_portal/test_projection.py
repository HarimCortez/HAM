from __future__ import annotations

from ham.requester_portal.projection import (
    mask_email,
    mask_phone,
    mask_street,
    masked_contact,
    status_wording,
)


def test_status_wording_step2_statuses():
    assert status_wording("SUBMITTED") == "We've received your request."
    assert "call you" in status_wording("NEEDS_PHONE_CHECK")
    assert "reviewing" in status_wording("AWAITING_APPROVAL")


def test_status_wording_cancelled_includes_reason_except_spam():
    text = status_wording("CANCELLED", cancel_reason="requester_withdrew")
    assert "closed" in text.lower()
    assert "You let us know" in text

    spam_text = status_wording("CANCELLED", cancel_reason="spam")
    assert "closed" in spam_text.lower()
    assert "always welcome" in spam_text


def test_status_wording_unknown_status_returns_empty():
    assert status_wording("SOME_FUTURE_STATUS") == ""


def test_mask_email():
    assert mask_email("doris.palmer@gmail.com") == "d•••@gmail.com"
    assert mask_email(None) == ""
    assert mask_email("not-an-email") == ""


def test_mask_phone():
    assert mask_phone("+13055550177") == "(•••) •••-0177"
    assert mask_phone(None) == ""
    assert mask_phone("12") == ""


def test_mask_street_never_reveals_the_address():
    assert mask_street("1400 NW Example Ave") == "Hidden"
    assert mask_street(None) == ""


def test_masked_contact_never_contains_email_phone_or_street_raw():
    result = masked_contact(
        email="doris.palmer@gmail.com",
        phone="+13055550177",
        line1="1400 NW Example Ave",
        city="Miami",
        postal_code="33125",
    )
    # Q-137: city and ZIP are shown, everything else masked.
    assert result.city == "Miami"
    assert result.postal_code == "33125"
    assert "doris.palmer" not in result.email
    assert "5550177" not in result.phone
    assert "1400" not in result.street
