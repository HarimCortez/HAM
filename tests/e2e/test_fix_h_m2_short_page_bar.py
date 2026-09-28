"""FIX-H M2 regression (step2-ui-visual-qa.md "Final re-check at f1d4fb9" M2 partial): on a
short public page the sticky `.action-bar` used to sit mid-screen with empty canvas below it,
because `.public-shell__content`/`.public-card` only ever sized to their own (short) content.
Below 1024, the card (and whichever box wraps the bar) now stretches to the full available
height and the bar's own top margin becomes the flexible space, so it settles at the viewport
bottom.

Covers R12 (page-not-available) and R8 (verify), the two screens named in the brief's test
line, at 390.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db(transaction=True)

MAX_GAP_TO_VIEWPORT_BOTTOM = 24


def _assert_bar_near_bottom(page):
    bar_bottom = page.eval_on_selector(".action-bar", "el => el.getBoundingClientRect().bottom")
    viewport_height = page.evaluate("window.innerHeight")
    gap = viewport_height - bar_bottom
    assert gap <= MAX_GAP_TO_VIEWPORT_BOTTOM, (
        f"action bar sits {gap}px above the viewport bottom "
        f"(bar bottom={bar_bottom}, viewport height={viewport_height}), "
        f"expected <= {MAX_GAP_TO_VIEWPORT_BOTTOM}px"
    )


def test_r12_bar_near_bottom_at_390(live_server):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 390, "height": 844})
        page = context.new_page()
        # R12 renders when a secure-page token can't be resolved to a real draft/request at
        # all (`request_help_secure_page`'s `services.link_owner_contact` returns None).
        page.goto(f"{live_server.url}/request-help/r/not-a-real-token")
        page.wait_for_selector(".action-bar")
        _assert_bar_near_bottom(page)
        context.close()
        browser.close()


def test_r8_bar_near_bottom_at_390(live_server):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 390, "height": 844})
        page = context.new_page()

        page.goto(f"{live_server.url}/request-help")
        page.click("text=Start")
        page.wait_for_url("**/request-help/step/need")
        page.check("input[name=need_category][value=roof_or_ceiling]")
        page.fill("#id_description", "FIX-H M2 test data.")
        page.click("text=Continue")
        page.wait_for_url("**/request-help/step/home")
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
        page.fill("#id_email", "fix-h-m2@example.org")
        page.check("input[name=contact_preference][value=email]")
        page.check("input[name=availability][value=any_time]")
        page.click("text=Continue")
        page.wait_for_url("**/request-help/step/review")
        page.check("input[name=attested_statements][value=owner_authority]")
        page.check("input[name=attested_statements][value=responsibility]")
        page.click("text=Send request")
        page.wait_for_url("**/request-help/verify")

        _assert_bar_near_bottom(page)
        context.close()
        browser.close()
