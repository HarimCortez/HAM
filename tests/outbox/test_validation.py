from __future__ import annotations

import uuid

import pytest

from ham.outbox.validation import PayloadPIIError, validate_payload


def test_ids_codes_counts_and_nesting_are_fine():
    validate_payload(
        {
            "project_id": str(uuid.uuid4()),
            "status": "confirmed",
            "count": 3,
            "nested": {"task_id": str(uuid.uuid4())},
            "list": [{"role": "VOLUNTEER"}, {"role": "PROJECT_LEADER"}],
        }
    )


def test_uuid_strings_do_not_false_positive_as_phone_numbers():
    # A UUID has enough digit runs that a careless phone regex could misfire.
    validate_payload({"id": str(uuid.uuid4()), "another_id": str(uuid.uuid4())})


@pytest.mark.parametrize(
    "value",
    [
        "someone@example.org",
        "+1 305 555 0100",
        "305-555-0100",
        "(305) 555-0100",
    ],
)
def test_email_or_phone_like_values_are_rejected(value):
    with pytest.raises(PayloadPIIError):
        validate_payload({"note": value})


def test_non_dict_payload_is_rejected():
    with pytest.raises(PayloadPIIError):
        validate_payload(["not", "a", "dict"])  # type: ignore[arg-type]


def test_non_string_key_is_rejected():
    with pytest.raises(PayloadPIIError):
        validate_payload({1: "x"})  # type: ignore[dict-item]
