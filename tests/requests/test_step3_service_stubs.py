"""S3.0: the `NotImplementedError` stubs in `ham.requests.services_questions` (approvals.md
§8.1; approvals-contracts.md §2) exist with the exact signatures S3.3 commits to. This only
pins "callable, raises NotImplementedError, doesn't explode on import" -- the real behavior is
S3.3's own test suite.

`ham.requests.services_decisions` (S3.2) is no longer a stub -- see
`tests/requests/test_s32_decisions.py` and friends for its real command bodies.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from ham.requests import services_questions as questions

# Every stub raises before ever touching `ctx` -- `None` stands in for whichever context type
# the real signature (approvals-contracts.md §2) declares, since this test only proves "not
# implemented yet", not real authorization.
_CTX: Any = None


@pytest.mark.parametrize(
    "call",
    [
        lambda: questions.ask_question(_CTX, request_id=uuid.uuid4(), question="What color?"),
        lambda: questions.answer_question(_CTX, question_id=uuid.uuid4(), answer="Blue"),
        lambda: questions.record_phone_answer(_CTX, question_id=uuid.uuid4(), answer="Blue"),
        lambda: questions.withdraw_question(_CTX, question_id=uuid.uuid4()),
    ],
)
def test_stub_raises_not_implemented(call):
    with pytest.raises(NotImplementedError):
        call()
