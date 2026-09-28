"""FIX-H N7 regression (step2-ui-visual-qa.md "Final re-check at f1d4fb9" N7): icon choice
cards (R3) used to split words mid-word at default text size -- "Townh/ouse",
"Apartm/ent or condo", "Mobile or manufa/ctured home" -- because `overflow-wrap: anywhere`
collapsed the label's min-content in a narrow (10.5em) column.

Fix: icon grids get a wider minimum column (`.choice-grid:has(.choice-card__icon)`, 15em), and
`.choice-card` label text uses `overflow-wrap: break-word; hyphens: auto` (with `lang="en"` on
`<html>`) instead of `anywhere`, plus `min-width: 0` on the label span so it can still shrink
and wrap/hyphenate rather than overflow the card (a real bug this test also caught while it was
being written: without `min-width: 0` the label overflowed the card instead of wrapping).

Asserts, on R3 at 390 and 1280:
  * no long option's label contains a whole word broken mid-word -- checked two ways: (a) the
    label's own `scrollWidth <= clientWidth` (no internal overflow), and (b) a direct check
    that "Townhouse", "Apartment" and "manufactured" each appear as an intact, unbroken
    substring of the label's rendered text (a hyphen followed by a line break is allowed;
    a silent mid-word split is not, since `element.innerText`/`textContent` would then show
    the word split into two pieces with no hyphen);
  * B2 still holds: no horizontal page scroll at 195px.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db(transaction=True)

WORDS_TO_CHECK = ["Townhouse", "Apartment", "manufactured"]


def _goto_r3(page, live_server):
    page.goto(f"{live_server.url}/request-help")
    page.click("text=Start")
    page.wait_for_url("**/request-help/step/need")
    page.check("input[name=need_category][value=roof_or_ceiling]")
    page.fill("#id_description", "FIX-H N7 test data.")
    page.click("text=Continue")
    page.wait_for_url("**/request-help/step/home")


_WORD_RECT_COUNT_JS = """
(word) => {
  const labels = document.querySelectorAll('#id_property_type .choice-card span');
  for (const label of labels) {
    for (const node of label.childNodes) {
      if (node.nodeType !== Node.TEXT_NODE) continue;
      const idx = node.textContent.indexOf(word);
      if (idx === -1) continue;
      const range = document.createRange();
      range.setStart(node, idx);
      range.setEnd(node, idx + word.length);
      return range.getClientRects().length;
    }
  }
  return null;
}
"""


def _assert_no_midword_breaks(page):
    labels = page.query_selector_all("#id_property_type .choice-card span")
    assert labels, "no property-type choice-card labels found"

    for label in labels:
        scroll_width = label.evaluate("el => el.scrollWidth")
        client_width = label.evaluate("el => el.clientWidth")
        assert scroll_width <= client_width + 1, (
            f"label {label.inner_text()!r} overflows its own box: "
            f"scrollWidth={scroll_width} > clientWidth={client_width}"
        )

    # Geometric check (the one that actually catches a mid-word/mid-line split): use the Range
    # API to measure just the word's own substring. `getClientRects()` returns one rect per
    # line a range is painted on -- more than one means the word itself was broken across
    # lines (raw split or hyphenated), not just that the whole label wrapped onto a second
    # line for other words.
    for word in WORDS_TO_CHECK:
        rect_count = page.evaluate(_WORD_RECT_COUNT_JS, word)
        assert rect_count is not None, f"couldn't find {word!r} in any property-type label"
        assert rect_count == 1, (
            f"{word!r} is split across {rect_count} lines (a mid-word/hyphenated break) "
            f"instead of fitting on one line"
        )


@pytest.mark.parametrize("width", [390, 1280])
def test_no_midword_breaks_in_property_type_cards(live_server, width):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": width, "height": 900})
        page = context.new_page()
        _goto_r3(page, live_server)
        _assert_no_midword_breaks(page)
        context.close()
        browser.close()


def test_no_horizontal_scroll_at_195px(live_server):
    """B2 must still hold once the icon grid's minimum column width grew (N7's other change)."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 195, "height": 844})
        page = context.new_page()
        _goto_r3(page, live_server)

        scroll_width = page.evaluate("document.documentElement.scrollWidth")
        inner_width = page.evaluate("window.innerWidth")
        assert scroll_width <= inner_width, (
            f"page scrolls sideways at 195px: scrollWidth={scroll_width} > innerWidth={inner_width}"
        )

        context.close()
        browser.close()
