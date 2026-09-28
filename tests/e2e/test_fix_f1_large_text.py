"""FIX-F1 B1 regression: the sticky `.action-bar` must not clip its primary button, and the
page must not scroll sideways, at large text sizes or very narrow widths. Always-on (no
opt-in marker), unlike the screenshot suites, so it runs in the normal `pytest` invocation --
this is the "proof" test the FIX-F1 brief asked for (step2-ui-visual-qa.md's B1/N3).

Covers R3 (home), R4 (safety), R5 (reaching-you), R6 (review) and R8 (verify) at:
  * 390 CSS px with the root font-size forced to 200% (32px) after DOMContentLoaded, and
  * a 195px-wide viewport (roughly what 390 CSS px looks like under a 200% *page* zoom, which
    Playwright can't drive directly -- see the sibling screenshot test for the same rationale).

At each screen we assert:
  * `getComputedStyle(document.documentElement).fontSize` is `'32px'` in the 200%-text
    condition (proves the init script actually ran -- N3's bug was a script that silently
    never applied);
  * `document.documentElement.scrollWidth <= window.innerWidth` (no horizontal scroll);
  * the primary button's right edge (`getBoundingClientRect().right`) is `<= window.innerWidth`
    (the button is fully reachable, not clipped off-screen by the action bar).
"""

from __future__ import annotations

import re

import pytest

pytestmark = pytest.mark.django_db(transaction=True)


def _latest_code_for(email: str) -> str:
    from django.core import mail

    from ham.jobs import run_due_jobs_now

    run_due_jobs_now()
    matches = [m for m in mail.outbox if m.to == [email]]
    assert matches, f"no email sent to {email!r}"
    body = str(matches[-1].body)
    match = re.search(r"(\d{3})\D?(\d{3})", body)
    assert match, f"couldn't find a 6-digit code in: {body!r}"
    return match.group(1) + match.group(2)


def _assert_action_bar_reachable(page, *, expect_32px_font: bool) -> None:
    if expect_32px_font:
        font_size = page.evaluate("getComputedStyle(document.documentElement).fontSize")
        assert font_size == "32px", f"200% text didn't apply: fontSize={font_size!r}"

    scroll_width = page.evaluate("document.documentElement.scrollWidth")
    inner_width = page.evaluate("window.innerWidth")
    assert scroll_width <= inner_width, (
        f"page scrolls sideways: scrollWidth={scroll_width} > innerWidth={inner_width}"
    )

    button_right = page.evaluate(
        "document.querySelector('.action-bar__inner .btn--primary').getBoundingClientRect().right"
    )
    assert button_right <= inner_width, (
        f"primary button clipped: right={button_right} > innerWidth={inner_width}"
    )


@pytest.mark.parametrize(
    "condition",
    [
        pytest.param(
            {"width": 390, "height": 844, "force_200pct_text": True}, id="390-200pct-text"
        ),
        pytest.param({"width": 195, "height": 844, "force_200pct_text": False}, id="195px-wide"),
    ],
)
def test_action_bar_reachable_across_wizard(live_server, settings, tmp_path, condition):
    from playwright.sync_api import sync_playwright

    settings.HAM_LOCAL_STORAGE_ROOT = str(tmp_path)
    settings.HAM_OBJECT_STORE_BACKEND = "ham.integrations.storage.local.LocalObjectStore"

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

        # R3 (home)
        page.check("input[name=relationship_to_property][value=owner]")
        page.fill("#id_line1", "1400 NW Example Ave")
        page.fill("#id_city", "Miami")
        page.fill("#id_state", "FL")
        page.fill("#id_postal_code", "33125")
        page.check("input[name=property_type][value=house]")
        _assert_action_bar_reachable(page, expect_32px_font=condition["force_200pct_text"])
        page.click("text=Continue")
        page.wait_for_url("**/request-help/step/safety")

        # R4 (safety)
        page.check("input[name=hazards][value=none_known]")
        _assert_action_bar_reachable(page, expect_32px_font=condition["force_200pct_text"])
        page.click("text=Continue")
        page.wait_for_url("**/request-help/step/reaching-you")

        # R5 (reaching-you)
        email = f"fix-f1-{condition['width']}@example.org"
        page.fill("#id_full_name", "FIX-F1 Test Requester")
        page.fill("#id_phone", "(305) 555-0142")
        page.fill("#id_email", email)
        page.check("input[name=contact_preference][value=email]")
        page.check("input[name=availability][value=any_time]")
        _assert_action_bar_reachable(page, expect_32px_font=condition["force_200pct_text"])
        page.click("text=Continue")
        page.wait_for_url("**/request-help/step/review")

        # R6 (review)
        page.check("input[name=attested_statements][value=owner_authority]")
        page.check("input[name=attested_statements][value=responsibility]")
        _assert_action_bar_reachable(page, expect_32px_font=condition["force_200pct_text"])
        page.click("text=Send request")
        page.wait_for_url("**/request-help/verify")

        # R8 (verify)
        _assert_action_bar_reachable(page, expect_32px_font=condition["force_200pct_text"])

        context.close()
        browser.close()
