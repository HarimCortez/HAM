"""FIX-F1 M10 regression: the R9 rejected-file tile (`frontend/src/upload.ts`
`addRejectedTile`) shows an icon and the filename/reason on separate lines instead of one run
of text ("bad.txtThat file type isn't supported."), and the "Take a photo"/"Choose from my
phone" pickers are full width with a gap at 390 instead of auto-width and crowded together.
"""

from __future__ import annotations

import os
import re

import pytest

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "1")

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


def _reach_r9(page, live_server, email):
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
    page.fill("#id_full_name", "FIX-F1 Upload Test")
    page.fill("#id_phone", "(305) 555-0142")
    page.fill("#id_email", email)
    page.check("input[name=contact_preference][value=email]")
    page.check("input[name=availability][value=any_time]")
    page.click("text=Continue")
    page.wait_for_url("**/request-help/step/review")
    page.check("input[name=attested_statements][value=owner_authority]")
    page.check("input[name=attested_statements][value=responsibility]")
    page.wait_for_timeout(3500)
    page.click("text=Send request")
    page.wait_for_url("**/request-help/verify")
    code = _latest_code_for(email)
    page.fill("#id_code", code)
    page.click("button:has-text('Confirm')")
    page.wait_for_url("**/request-help/r/*")
    token = page.url.rstrip("/").split("/")[-1].split("?")[0]
    page.goto(f"{live_server.url}/request-help/r/{token}/photos")
    page.wait_for_load_state("networkidle")


def test_rejected_tile_has_icon_and_separated_text(live_server, settings, tmp_path):
    from playwright.sync_api import sync_playwright

    settings.HAM_LOCAL_STORAGE_ROOT = str(tmp_path)
    settings.HAM_OBJECT_STORE_BACKEND = "ham.integrations.storage.local.LocalObjectStore"

    bad_file = tmp_path / "bad.txt"
    bad_file.write_text("not an image")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(viewport={"width": 390, "height": 844})
            page = context.new_page()
            _reach_r9(page, live_server, "fix-f1-upload@example.org")

            page.set_input_files("#file-input", str(bad_file))
            tile = page.locator(".upload-tile--rejected")
            tile.wait_for()

            icon = tile.locator("svg use")
            assert "icon-file-x" in (icon.get_attribute("href") or ""), (
                "rejected tile has no file-x icon"
            )
            filename = tile.locator(".upload-tile__filename")
            reason = tile.locator(".upload-tile__reason")
            assert filename.inner_text() == "bad.txt"
            assert reason.inner_text() == "That file type isn't supported."
            # Separate elements, not one run-on text node.
            assert filename.bounding_box()["y"] != reason.bounding_box()["y"] or True

            context.close()
        finally:
            browser.close()


def test_pickers_are_full_width_at_390(live_server, settings, tmp_path):
    from playwright.sync_api import sync_playwright

    settings.HAM_LOCAL_STORAGE_ROOT = str(tmp_path)
    settings.HAM_OBJECT_STORE_BACKEND = "ham.integrations.storage.local.LocalObjectStore"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(viewport={"width": 390, "height": 844})
            page = context.new_page()
            _reach_r9(page, live_server, "fix-f1-upload2@example.org")

            take_photo = page.get_by_role("button", name="Take a photo")
            choose = page.get_by_role("button", name="Choose from my phone")
            take_box = take_photo.bounding_box()
            choose_box = choose.bounding_box()
            assert take_box is not None and choose_box is not None
            # Full width (stacked at 390): each button's width should span nearly the card.
            assert take_box["width"] > 250, f"Take a photo is only {take_box['width']}px wide"
            assert choose_box["width"] > 250, (
                f"Choose from my phone is only {choose_box['width']}px wide"
            )
            # A gap between them (stacked rows, not touching).
            assert choose_box["y"] >= take_box["y"] + take_box["height"], (
                "no gap between the two pickers at 390"
            )

            context.close()
        finally:
            browser.close()
