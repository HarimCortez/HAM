"""FIX-H M3 regression (step2-ui-visual-qa.md "Final re-check at f1d4fb9" M3 partial): R2's
"What kind of help?" category cards had no icons, unlike R3/R4/R5 (design-system/screens/
intake.md R2: house, droplet, plug-zap, door-closed, layers, accessibility, paint-roller,
trees, circle-help).

Asserts every category choice-card on R2 has a visible `.choice-card__icon` <svg>, that each
one references a real symbol id defined in `icons.svg` (not a typo that silently renders
nothing), and that "Something else or not sure" is full width and last.
"""

from __future__ import annotations

import re

import pytest

pytestmark = pytest.mark.django_db(transaction=True)


def _icon_symbol_ids() -> set[str]:
    from django.conf import settings

    icons_path = settings.BASE_DIR / "ham" / "web" / "static" / "web" / "icons.svg"
    text = icons_path.read_text()
    return set(re.findall(r'<symbol id="icon-([a-z0-9-]+)"', text))


def test_r2_category_cards_have_real_icons(live_server):
    from playwright.sync_api import sync_playwright

    symbol_ids = _icon_symbol_ids()
    assert symbol_ids, "couldn't find any icon symbols in icons.svg"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 390, "height": 900})
        page = context.new_page()
        page.goto(f"{live_server.url}/request-help")
        page.click("text=Start")
        page.wait_for_url("**/request-help/step/need")

        cards = page.query_selector_all("#id_need_category .choice-card")
        assert len(cards) == 9, f"expected 9 category cards, found {len(cards)}"

        for card in cards:
            icon = card.query_selector(".choice-card__icon use")
            assert icon is not None, "a category card has no .choice-card__icon"
            href = icon.get_attribute("href") or ""
            assert "#icon-" in href, f"icon has no #icon-<name> href: {href!r}"
            symbol_id = href.split("#icon-", 1)[1]
            assert symbol_id in symbol_ids, (
                f"choice-card icon references '#icon-{symbol_id}', which isn't defined in "
                f"icons.svg -- it would silently render nothing"
            )

        last_card = cards[-1]
        assert "Something else" in last_card.inner_text()
        assert "choice-card--full" in (last_card.get_attribute("class") or "")

        context.close()
        browser.close()
