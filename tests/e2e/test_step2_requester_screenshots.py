"""Visual QA screenshots for S2.7 (public requester screens R1-R12). Opt-in
(`HAM_SCREENSHOTS=1`), same technique as `tests/e2e/test_step1_final_screenshots.py`: a real
browser (Playwright) against `live_server`, with the form driven exactly like a person would
use it. Uses seeded fake data only (no real people), per the S2.7 handoff brief.

    HAM_SCREENSHOTS=1 PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers \\
        DATABASE_URL=... DJANGO_SETTINGS_MODULE=config.settings.test \\
        pytest tests/e2e/test_step2_requester_screenshots.py -p no:randomly
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("HAM_SCREENSHOTS") != "1",
    reason="opt-in visual QA pass; set HAM_SCREENSHOTS=1 to run (see module docstring)",
)
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "1")

OUT_DIR = Path(__file__).resolve().parents[2] / "docs" / "ux" / "screenshots" / "step2"
VIEWPORTS = {"390": (390, 844), "1280": (1280, 900)}


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


@pytest.mark.django_db(transaction=True)
def test_requester_screens(live_server, settings, tmp_path):
    from playwright.sync_api import sync_playwright

    settings.HAM_LOCAL_STORAGE_ROOT = str(tmp_path)
    settings.HAM_OBJECT_STORE_BACKEND = "ham.integrations.storage.local.LocalObjectStore"

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for label, (width, height) in VIEWPORTS.items():
            context = browser.new_context(viewport={"width": width, "height": height})
            page = context.new_page()

            # R1
            page.goto(f"{live_server.url}/request-help")
            page.screenshot(path=str(OUT_DIR / f"request-start-{label}.png"))

            page.click("text=Start")
            page.wait_for_url("**/request-help/step/need")

            # R2 -- "the form"
            page.check("input[name=need_category][value=roof_or_ceiling]")
            page.fill(
                "#id_description",
                "Water comes through the bedroom ceiling when it rains (visual QA seed data).",
            )
            page.screenshot(path=str(OUT_DIR / f"request-form-{label}.png"), full_page=True)
            page.click("text=Continue")
            page.wait_for_url("**/request-help/step/home")

            # R3
            page.check("input[name=relationship_to_property][value=owner]")
            page.fill("#id_line1", "1400 NW Example Ave")
            page.fill("#id_city", "Miami")
            page.fill("#id_postal_code", "33125")
            page.fill("#id_state", "FL")
            page.check("input[name=property_type][value=house]")
            page.click("text=Continue")
            page.wait_for_url("**/request-help/step/safety")

            # R4
            page.check("input[name=hazards][value=none_known]")
            page.click("text=Continue")
            page.wait_for_url("**/request-help/step/reaching-you")

            # R5
            email = f"qa-{label}@example.org"
            page.fill("#id_full_name", "Visual QA Requester")
            page.fill("#id_phone", "(305) 555-0142")
            page.fill("#id_email", email)
            page.check("input[name=contact_preference][value=email]")
            page.check("input[name=availability][value=any_time]")
            page.click("text=Continue")
            page.wait_for_url("**/request-help/step/review")

            # R6
            page.check("input[name=attested_statements][value=owner_authority]")
            page.check("input[name=attested_statements][value=responsibility]")
            page.screenshot(path=str(OUT_DIR / f"request-review-{label}.png"), full_page=True)
            # Anti-abuse minimum-fill-time (docs/ux/intake.md §9): stay on the review step
            # past RULES.intake.INTAKE_MIN_FILL_TIME before Send, or the submission silently
            # no-ops (same success page, no code sent) exactly like a real too-fast bot would.
            page.wait_for_timeout(3500)
            page.click("text=Send request")
            page.wait_for_url("**/request-help/verify")

            # R8
            page.screenshot(path=str(OUT_DIR / f"verify-code-{label}.png"))
            code = _latest_code_for(email)
            page.fill("#id_code", code)
            page.click("button:has-text('Confirm')")
            page.wait_for_url("**/request-help/r/*")

            # R7 (welcome) / R10
            page.screenshot(path=str(OUT_DIR / f"request-received-{label}.png"), full_page=True)
            page.goto(page.url.split("?")[0])
            page.screenshot(path=str(OUT_DIR / f"secure-page-{label}.png"), full_page=True)

            context.close()

        # R7N: the "I don't use email" confirmation (its own short flow, 390 only).
        context = browser.new_context(viewport={"width": 390, "height": 844})
        page = context.new_page()
        page.goto(f"{live_server.url}/request-help")
        page.click("text=Start")
        page.wait_for_url("**/request-help/step/need")
        page.check("input[name=need_category][value=plumbing_or_water]")
        page.fill("#id_description", "Kitchen sink leaks (visual QA seed data).")
        page.click("text=Continue")
        page.wait_for_url("**/request-help/step/home")
        page.check("input[name=relationship_to_property][value=owner]")
        page.fill("#id_line1", "20 SW Example St")
        page.fill("#id_city", "Miami")
        page.fill("#id_postal_code", "33130")
        page.fill("#id_state", "FL")
        page.check("input[name=property_type][value=house]")
        page.click("text=Continue")
        page.wait_for_url("**/request-help/step/safety")
        page.check("input[name=hazards][value=none_known]")
        page.click("text=Continue")
        page.wait_for_url("**/request-help/step/reaching-you")
        page.fill("#id_full_name", "No Email QA Requester")
        page.fill("#id_phone", "(305) 555-0177")
        page.check("#id_no_email")
        # FIX-E made availability a required field on this step; this screenshot script
        # predates that and never selected one, so R5 -> R6 now 422s (fixed here, test-only --
        # the production requirement itself is FIX-E's).
        page.check("input[name=availability][value=any_time]")
        page.click("text=Continue")
        page.wait_for_url("**/request-help/step/review")
        page.check("input[name=attested_statements][value=owner_authority]")
        page.check("input[name=attested_statements][value=responsibility]")
        page.wait_for_timeout(3500)
        page.click("text=Send request")
        page.wait_for_url("**/request-help/saved")
        page.screenshot(path=str(OUT_DIR / "request-saved-390.png"), full_page=True)
        context.close()

        browser.close()


@pytest.mark.django_db(transaction=True)
def test_requester_screens_200pct_text(live_server, settings, tmp_path):
    """FIX-C (step 2 fix round): 390x844 with the root font-size doubled, to prove B1 (the
    sticky action bar's Back relocation / no clipped primary) and B2 (no horizontal scroll on
    long unbroken values) hold at 200% text, not only at 200% *page* zoom (which Playwright
    can't drive directly -- `document.documentElement.style.fontSize` is the same "200% text"
    condition S§0.2 describes: the browser's own text-size setting, independent of layout
    zoom)."""
    from playwright.sync_api import sync_playwright

    settings.HAM_LOCAL_STORAGE_ROOT = str(tmp_path)
    settings.HAM_OBJECT_STORE_BACKEND = "ham.integrations.storage.local.LocalObjectStore"

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 390, "height": 844})
        page = context.new_page()
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
            "Water comes through the bedroom ceiling when it rains (visual QA seed data).",
        )
        page.click("text=Continue")
        page.wait_for_url("**/request-help/step/home")

        # R3 at 200% text: proves the fieldset reset (B3) restores the 2-column choice grid
        # and the state "Change" control doesn't overflow.
        page.check("input[name=relationship_to_property][value=owner]")
        page.fill("#id_line1", "1400 NW Example Ave")
        page.fill("#id_city", "Miami")
        page.fill("#id_postal_code", "33125")
        page.fill("#id_state", "FL")
        page.check("input[name=property_type][value=house]")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), (
            "R3 scrolls sideways at 200% text"
        )
        page.screenshot(path=str(OUT_DIR / "request-home-390-text200.png"), full_page=True)
        page.click("text=Continue")
        page.wait_for_url("**/request-help/step/safety")

        page.check("input[name=hazards][value=none_known]")
        page.click("text=Continue")
        page.wait_for_url("**/request-help/step/reaching-you")

        email = "qa-text200@example.org"
        page.fill("#id_full_name", "Visual QA Requester")
        page.fill("#id_phone", "(305) 555-0142")
        page.fill("#id_email", email)
        page.check("input[name=contact_preference][value=email]")
        page.check("input[name=availability][value=any_time]")
        page.click("text=Continue")
        page.wait_for_url("**/request-help/step/review")

        # R6 at 200% text: proves the action bar (B1) keeps Send reachable and the email/phone
        # values (B2) wrap instead of forcing the page wider than the viewport.
        page.check("input[name=attested_statements][value=owner_authority]")
        page.check("input[name=attested_statements][value=responsibility]")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), (
            "R6 scrolls sideways at 200% text"
        )
        page.screenshot(path=str(OUT_DIR / "request-review-390-text200.png"), full_page=True)

        context.close()
        browser.close()
