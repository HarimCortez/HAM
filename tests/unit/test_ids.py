from __future__ import annotations

import time
import uuid

from ham.platform.ids import uuid7


def test_uuid7_is_a_valid_uuid_with_version_7():
    value = uuid7()
    assert isinstance(value, uuid.UUID)
    assert value.version == 7


def test_uuid7_values_sort_by_creation_time():
    first = uuid7()
    time.sleep(0.005)
    second = uuid7()
    assert str(first) < str(second)


def test_uuid7_values_are_unique():
    values = {uuid7() for _ in range(1000)}
    assert len(values) == 1000
