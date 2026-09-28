"""FIX-H N6 regression (step2-ui-visual-qa.md "Final re-check at f1d4fb9"): under the sticky
action bar's own `@container (max-width: 22em)` (200% text / 195px-wide "200% zoom"), stacking
BOTH Back and the primary took up to a third of a short viewport and covered the fields while
typing. Per the B1 spec, under that width the bar should hold the primary only -- Back becomes
an ordinary text link in the page flow above the bar (`.wizard-back-link`), toggled by the same
container query, with no JS required.

Covers R3 (home) and R6 (review), the two screens named in the brief's test line, at:
  * 390 CSS px with the root font-size forced to 200% (32px) after DOMContentLoaded, and
  * a 195px-wide viewport (~390 CSS px at 200% page zoom, which Playwright can't drive
    directly -- same rationale as the sibling FIX-F1 large-text test).

Asserts, at each screen:
  * the bar's rendered height is <= 110px (390 + 200% text) / <= 90px (195px);
  * the page never scrolls sideways;
  * Back is reachable and visible (as the in-flow link, not inside the now primary-only bar).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db(transaction=True)

MAX_BAR_HEIGHT_200PCT_TEXT = 110
MAX_BAR_HEIGHT_195PX = 90


def _goto_r3(page, live_server):
    page.goto(f"{live_server.url}/request-help")
    page.click("text=Start")
    page.wait_for_url("**/request-help/step/need")
    page.check("input[name=need_category][value=roof_or_ceiling]")
    page.fill(
        "#id_description",
        "Water comes through the bedroom ceiling when it rains (FIX-H test data).",
    )
    page.click("text=Continue")
    page.wait_for_url("**/request-help/step/home")


def _goto_r6(page, live_server, *, email: str):
    _goto_r3(page, live_server)
    page.check("input[name=relationship_to_property][value=owner]")
    page.fill("#id_line1", "1400 NW Example Ave")
    page.fill("#id_city", "Miami")
    page.fill("#id_state", "FL")
    page.fill("#id_postal_code", "33125")
    page.check("input[name=property_type][value=house]")
    page.click("text=Continue")
    page.wait_for_url("**/request-help/step/safety")
    page.check("input[name=hazards][value=none_known]")
    page.click("text=Continue")
    page.wait_for_url("**/request-help/step/reaching-you")
    page.fill("#id_full_name", "FIX-H Test Requester")
    page.fill("#id_phone", "(305) 555-0142")
    page.fill("#id_email", email)
    page.check("input[name=contact_preference][value=email]")
    page.check("input[name=availability][value=any_time]")
    page.click("text=Continue")
    page.wait_for_url("**/request-help/step/review")


def _assert_bar_and_back(page, *, max_bar_height: int):
    scroll_width = page.evaluate("document.documentElement.scrollWidth")
    inner_width = page.evaluate("window.innerWidth")
    assert scroll_width <= inner_width, (
        f"page scrolls sideways: scrollWidth={scroll_width} > innerWidth={inner_width}"
    )

    bar_height = page.eval_on_selector(".action-bar", "el => el.getBoundingClientRect().height")
    assert bar_height <= max_bar_height, (
        f"action bar is {bar_height}px tall, expected <= {max_bar_height}px"
    )

    # The bar itself must hold only the primary now -- Back's in-bar twin is hidden.
    back_in_bar_visible = page.eval_on_selector(
        ".action-bar__inner .action-bar__back", "el => el.offsetParent !== null"
    )
    assert not back_in_bar_visible, "Back should not render inside the bar under 22em"

    # Its in-flow twin must be visible and reachable instead.
    back_link = page.query_selector(".wizard-back-link a")
    assert back_link is not None, "no in-flow Back link found"
    assert back_link.is_visible(), "in-flow Back link is not visible"
    back_rect = back_link.bounding_box()
    assert back_rect is not None and back_rect["y"] >= 0, "Back link is off-screen"


@pytest.mark.parametrize(
    "condition",
    [
        pytest.param(
            {
                "width": 390,
                "height": 844,
                "force_200pct_text": True,
                "max_height": MAX_BAR_HEIGHT_200PCT_TEXT,
            },
            id="390-200pct-text",
        ),
        pytest.param(
            {
                "width": 195,
                "height": 844,
                "force_200pct_text": False,
                "max_height": MAX_BAR_HEIGHT_195PX,
            },
            id="195px-wide",
        ),
    ],
)
def test_action_bar_holds_primary_only_on_r3(live_server, condition):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": condition["width"], "height": condition["height"]}
        )
        page = context.new_page()
        if condition["force_200pct_text"]:
            page.add_init_script(
                "document.addEventListener('DOMContentLoaded', () => {"
                " document.documentElement.style.fontSize = '200%';"
                "});"
            )

        _goto_r3(page, live_server)
        _assert_bar_and_back(page, max_bar_height=condition["max_height"])

        context.close()
        browser.close()


@pytest.mark.parametrize(
    "condition",
    [
        pytest.param(
            {
                "width": 390,
                "height": 844,
                "force_200pct_text": True,
                "max_height": MAX_BAR_HEIGHT_200PCT_TEXT,
            },
            id="390-200pct-text",
        ),
        pytest.param(
            {
                "width": 195,
                "height": 844,
                "force_200pct_text": False,
                "max_height": MAX_BAR_HEIGHT_195PX,
            },
            id="195px-wide",
        ),
    ],
)
def test_action_bar_holds_primary_only_on_r6(live_server, condition):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": condition["width"], "height": condition["height"]}
        )
        page = context.new_page()
        if condition["force_200pct_text"]:
            page.add_init_script(
                "document.addEventListener('DOMContentLoaded', () => {"
                " document.documentElement.style.fontSize = '200%';"
                "});"
            )

        email = f"fix-h-n6-{condition['width']}@example.org"
        _goto_r6(page, live_server, email=email)
        _assert_bar_and_back(page, max_bar_height=condition["max_height"])

        context.close()
        browser.close()
