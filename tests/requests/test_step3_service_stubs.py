"""S3.0: the `NotImplementedError` stubs in `ham.requests.services_decisions`
(approvals.md §8.1; approvals-contracts.md §2) exist with the exact signatures S3.2 commits
to. This only pins "callable, raises NotImplementedError, doesn't explode on import" -- the
real behavior is S3.2's own test suite.

S3.3 (`ham.requests.services_questions`) implemented its four stubs (`ask_question`,
`answer_question`, `record_phone_answer`, `withdraw_question`) -- see
`tests/requests/test_s33_questions.py` for their real behavior; they are removed from this
stub-only list (S3.3, coordination note per the wave brief: "if you need a hook in someone
else's file, add a minimal one and flag it in your hand-back").
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from ham.requests import services_decisions as decisions

# Every stub raises before ever touching `ctx` -- `None` stands in for whichever context type
# the real signature (approvals-contracts.md §2) declares, since this test only proves "not
# implemented yet", not real authorization.
_CTX: Any = None


@pytest.mark.parametrize(
    "call",
    [
        lambda: decisions.approve_request(_CTX, request_id=uuid.uuid4(), route="pastoral"),
        lambda: decisions.reject_request(
            _CTX,
            request_id=uuid.uuid4(),
            route="pastoral",
            reason_code="another_reason",
            message="Sorry",
        ),
        lambda: decisions.review_urgency(_CTX, request_id=uuid.uuid4(), certify=True),
        lambda: decisions.request_reconsideration(_CTX),
        lambda: decisions.record_reconsideration_by_phone(_CTX, request_id=uuid.uuid4()),
        lambda: decisions.decide_reconsideration(
            _CTX, request_id=uuid.uuid4(), approve=True, reason="ok"
        ),
        lambda: decisions.finalize_rejection(_CTX, request_id=uuid.uuid4()),
        lambda: decisions.record_decision_phoned(_CTX, request_id=uuid.uuid4()),
        lambda: decisions.change_category(
            _CTX, request_id=uuid.uuid4(), need_category="roof_or_ceiling"
        ),
        lambda: decisions.undo_decision(_CTX, approval_id=uuid.uuid4()),
    ],
)
def test_stub_raises_not_implemented(call):
    with pytest.raises(NotImplementedError):
        call()
