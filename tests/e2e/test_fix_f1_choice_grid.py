"""FIX-F1 B3 regression: the R3 "Type of home" choice grid must render 2 columns at 390 --
`minmax(min(100%, 11em), 1fr)` needed 360px for 2 tracks, but the card's content box at 390 is
only 358px, so it silently fell back to 1 column. `10.5em` fits.

Also covers FIX-F1 B2: at 195px, a long unbroken word inside a `.choice-card` (e.g. "Mobile or
manufactured home"'s "manufactured") must break instead of spilling past the card border.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db(transaction=True)


def test_property_type_grid_is_two_columns_at_390(live_server):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(viewport={"width": 390, "height": 844})
            page = context.new_page()
            page.goto(f"{live_server.url}/request-help")
            page.click("text=Start")
            page.wait_for_url("**/request-help/step/need")
            page.check("input[name=need_category][value=roof_or_ceiling]")
            page.fill(
                "#id_description",
                "Water comes through the bedroom ceiling when it rains (FIX-F1 test data).",
            )
            page.click("text=Continue")
            page.wait_for_url("**/request-help/step/home")

            cards = page.locator("input[name=property_type]").locator("xpath=..")
            tops = [
                page.evaluate("el => el.getBoundingClientRect().top", card_handle)
                for card_handle in cards.element_handles()
            ]
            assert len(tops) >= 2, "expected at least 2 property-type choice cards"
            # 2 columns => the first two cards share the same row (same top).
            assert tops[0] == tops[1], (
                f"property-type choice cards aren't in the same row at 390: {tops}"
            )

            context.close()
        finally:
            browser.close()


def test_choice_card_long_word_does_not_overflow_at_195px(live_server):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(viewport={"width": 195, "height": 844})
            page = context.new_page()
            page.goto(f"{live_server.url}/request-help")
            page.click("text=Start")
            page.wait_for_url("**/request-help/step/need")
            page.check("input[name=need_category][value=roof_or_ceiling]")
            page.fill(
                "#id_description",
                "Water comes through the bedroom ceiling when it rains (FIX-F1 test data).",
            )
            page.click("text=Continue")
            page.wait_for_url("**/request-help/step/home")

            card = page.locator("label.choice-card", has_text="manufactured").first
            card_box = card.bounding_box()
            span_box = card.locator("span").bounding_box()
            assert card_box is not None and span_box is not None
            assert span_box["x"] + span_box["width"] <= card_box["x"] + card_box["width"] + 1, (
                "the choice-card text spills past the card border at 195px"
            )
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), (
                "page scrolls sideways at 195px"
            )

            context.close()
        finally:
            browser.close()
