"""FIX-F1 B3 regression (superseded in part by FIX-H N7 -- see below): the R3 "Type of home"
choice grid must render at a *consistent, predictable* column count at 390 -- originally
`minmax(min(100%, 11em), 1fr)` needed 360px for 2 tracks, but the card's content box at 390 is
only 358px, so it silently fell back to 1 column; `10.5em` fixed that for plain-text grids.

FIX-H N7 changed the *icon*-card grids specifically (R3/R4/R5 all have icons; R2's category
grid gained icons too) to a wider `15em` minimum column instead, because 10.5em/icon-card
combination left too little room for the label text and caused mid-word breaks ("Townh/ouse").
15em deliberately gives 1 column at 390 (this test) and 2 columns in the 640px main column at
>=1280 (see the second test below) -- confirmed against design-system/screens/intake.md R3.
Icon-less grids (none remain as of FIX-H) would still get the tighter 10.5em/2-column
treatment.

Also covers FIX-F1 B2: at 195px, a long unbroken word inside a `.choice-card` (e.g. "Mobile or
manufactured home"'s "manufactured") must break instead of spilling past the card border.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db(transaction=True)


def _goto_r3(page, live_server):
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


def _property_type_card_tops(page):
    cards = page.locator("input[name=property_type]").locator("xpath=..")
    return [
        page.evaluate("el => el.getBoundingClientRect().top", card_handle)
        for card_handle in cards.element_handles()
    ]


def test_property_type_grid_is_one_column_at_390(live_server):
    """FIX-H N7: the icon-card grid's wider (15em) minimum column gives 1 column at 390 -- the
    room a label like "Mobile or manufactured home" needs to stay on one line without
    breaking mid-word (see test_fix_h_n7_choice_card_wrap.py for the mid-word-break assertion
    itself)."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(viewport={"width": 390, "height": 844})
            page = context.new_page()
            _goto_r3(page, live_server)

            tops = _property_type_card_tops(page)
            assert len(tops) >= 2, "expected at least 2 property-type choice cards"
            # 1 column => every card sits in its own row (strictly increasing top).
            assert tops == sorted(set(tops)), (
                f"property-type choice cards share a row at 390 (expected 1 column): {tops}"
            )

            context.close()
        finally:
            browser.close()


def test_property_type_grid_is_two_columns_at_1280(live_server):
    """FIX-H N7: at >=1280, inside the 640px wizard main column, the wider 15em minimum still
    fits 2 columns."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            _goto_r3(page, live_server)

            tops = _property_type_card_tops(page)
            assert len(tops) >= 2, "expected at least 2 property-type choice cards"
            # 2 columns => the first two cards share the same row (same top).
            assert tops[0] == tops[1], (
                f"property-type choice cards aren't in the same row at 1280: {tops}"
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
