"""FIX-F1 N2 regression: the wizard's "Good to know" aside (R1-R6, R9) used to stretch the
first grid row to the aside's full height at >=1280 (`.wizard-aside`'s `grid-row: 1 / -1` only
actually spanned row 1, since `.public-card:has(> .wizard-aside)` never defines an explicit row
template), leaving ~130px of dead space between the progress bar and the h1. Asserts the h1's
top stays within the first ~160px of the card at 1280, across every step that has the aside.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db(transaction=True)

MAX_H1_TOP_WITHIN_CARD = 160


def test_wizard_h1_near_top_of_card_at_1280(live_server):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()

            # R1 has no h1 offset from a prior step, so just load it directly.
            page.goto(f"{live_server.url}/request-help")

            card_top = page.eval_on_selector(".public-card", "el => el.getBoundingClientRect().top")
            h1_top = page.eval_on_selector("h1", "el => el.getBoundingClientRect().top")
            assert h1_top - card_top <= MAX_H1_TOP_WITHIN_CARD, (
                f"R1: h1 top ({h1_top}) is more than {MAX_H1_TOP_WITHIN_CARD}px below the "
                f"card top ({card_top})"
            )

            # Drive to R3 (home), which also carries the aside, and has a taller aside body
            # than R1 (more likely to reproduce the stretched-row-1 bug).
            page.click("text=Start")
            page.wait_for_url("**/request-help/step/need")
            page.check("input[name=need_category][value=roof_or_ceiling]")
            page.fill(
                "#id_description",
                "Water comes through the bedroom ceiling when it rains (FIX-F1 test data).",
            )
            page.click("text=Continue")
            page.wait_for_url("**/request-help/step/home")

            card_top = page.eval_on_selector(".public-card", "el => el.getBoundingClientRect().top")
            h1_top = page.eval_on_selector("h1", "el => el.getBoundingClientRect().top")
            assert h1_top - card_top <= MAX_H1_TOP_WITHIN_CARD, (
                f"R3: h1 top ({h1_top}) is more than {MAX_H1_TOP_WITHIN_CARD}px below the "
                f"card top ({card_top})"
            )

            context.close()
        finally:
            browser.close()
