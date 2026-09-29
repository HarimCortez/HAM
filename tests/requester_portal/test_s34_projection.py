"""S3.4: step-3 requester-facing wording/chips (docs/ux/approvals.md §6 R14/R15/R17/R18;
design-system/components.md §26a). Pure -- no DB.
"""

from __future__ import annotations

import datetime as dt

from ham.requester_portal import projection


def test_approved_chip_and_sentence():
    chip = projection.REQUESTER_STATUS_CHIPS["APPROVED"]
    assert chip == ("Approved", "success", "circle-check")
    assert projection.approved_sentence(after_reconsideration=False) == (
        "Good news: your request is approved."
    )
    assert "after taking another look" in projection.approved_sentence(after_reconsideration=True)


def test_approved_next_steps_keep_the_section_11_line():
    steps = projection.APPROVED_NEXT_STEPS
    assert len(steps) == 3
    assert steps[0] == "Someone from HAM will call you to arrange a visit to look at the work."
    assert steps[1] == "The visit helps us plan; it doesn't yet promise the work."
    assert steps[2] == "You don't need to do anything right now."


def test_urgent_certified_alert_mentions_911():
    assert "911" in projection.URGENT_CERTIFIED_ALERT


def test_rejected_chip_open_vs_final():
    assert projection.rejected_chip(closed=False) == ("Not approved", "neutral", "circle-x")
    assert projection.rejected_chip(closed=True) == ("Closed", "neutral", "ban")


def test_rejected_open_sentence_is_fixed_and_never_carries_the_reason():
    sentence = projection.rejected_open_sentence()
    assert "we aren't able to help with this one" in sentence


def test_rejected_final_sentence_after_reconsideration_vs_window_passed():
    after = projection.rejected_final_sentence(after_reconsideration=True)
    passed = projection.rejected_final_sentence(after_reconsideration=False)
    assert "looked at your request again" in after
    assert after != passed
    assert passed == "We weren't able to help with this request."


def test_reconsideration_pending_chip_and_sentence():
    chip = projection.REQUESTER_STATUS_CHIPS["RECONSIDERATION_PENDING"]
    assert chip == ("Taking another look", "info", "rotate-ccw")
    assert projection.reconsideration_pending_sentence() == (
        "We're taking another look at your request."
    )


def test_reconsider_ask_line_formats_the_church_local_date():
    line = projection.reconsider_ask_line(dt.date(2026, 11, 5))
    assert line == "You can ask until Thu, Nov 5."


def test_no_projection_function_ever_takes_a_decider_identity_or_route():
    """Q-171: the module's whole public surface only ever takes an outcome/stage/flag -- never
    an `Approval` row, a user id, or a route. A regression here would be a new function
    signature accepting one of those, which this test can't detect by introspection alone, so
    it instead pins the exact, closed set of step-3 wording functions this module exports."""
    exported = set(projection.__all__)
    expected_step3 = {
        "APPROVED_NEXT_STEPS",
        "REJECTED_FINAL_NEXT_STEP",
        "REJECTED_SYMPATHY_LINE",
        "RECONSIDER_OFFER_LINE",
        "RECONSIDERATION_PENDING_NEXT_STEP",
        "URGENT_CERTIFIED_ALERT",
        "approved_sentence",
        "reconsideration_pending_sentence",
        "reconsider_ask_line",
        "rejected_chip",
        "rejected_final_sentence",
        "rejected_open_sentence",
    }
    assert expected_step3 <= exported
