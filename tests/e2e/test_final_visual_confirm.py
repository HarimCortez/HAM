"""Visual QA confirmation at 5f3f64e (docs/ux/reviews/step2-ui-visual-qa.md):

* NM1: choice-card labels on R2/R3 must not break mid-word at 390 + 200% text or at 195px
  (the decorative icon is dropped when the grid is narrow).
* NM2: the leadership media viewer must not scroll sideways for a large photo, and has an h1.
* NM3: Pastor Home must not scroll sideways at 390 + 200% text, and every bottom-nav tab
  (incl. "More") must stay reachable.
"""

from __future__ import annotations

import io
import os
import uuid

import pytest

# Same as the other live-server Playwright files: the sync Playwright API runs an event loop
# in this thread, which trips Django's async-safety check for ORM calls made between pages.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "1")

pytestmark = pytest.mark.django_db(transaction=True)

_TEXT_200_JS = (
    "document.addEventListener('DOMContentLoaded', () => {"
    " document.documentElement.style.fontSize = '200%'; });"
)

_WORD_RECT_COUNT_JS = """
([selector, word]) => {
  for (const label of document.querySelectorAll(selector)) {
    const walker = document.createTreeWalker(label, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
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

_MODES = [
    pytest.param({"width": 390, "height": 844, "text200": True}, id="390-200pct-text"),
    pytest.param({"width": 195, "height": 422, "text200": False}, id="195px-wide"),
]


def _new_page(p, mode):
    browser = p.chromium.launch()
    context = browser.new_context(viewport={"width": mode["width"], "height": mode["height"]})
    if mode["text200"]:
        context.add_init_script(_TEXT_200_JS)
    return browser, context, context.new_page()


def _assert_no_sideways_scroll(page, where):
    sw = page.evaluate("document.documentElement.scrollWidth")
    iw = page.evaluate("window.innerWidth")
    assert sw <= iw, f"{where}: page scrolls sideways (scrollWidth={sw} > innerWidth={iw})"


def _assert_words_on_one_line(page, selector, words):
    for word in words:
        count = page.evaluate(_WORD_RECT_COUNT_JS, [selector, word])
        assert count is not None, f"{word!r} not found under {selector}"
        assert count == 1, f"{word!r} is broken across {count} lines"


@pytest.mark.parametrize("mode", _MODES)
def test_choice_cards_do_not_break_words_at_large_text(live_server, mode):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser, context, page = _new_page(p, mode)
        page.goto(f"{live_server.url}/request-help")
        page.click("text=Start")
        page.wait_for_url("**/request-help/step/need")
        _assert_no_sideways_scroll(page, "R2")
        _assert_words_on_one_line(page, ".choice-card", ["Plumbing", "Electrical", "Something"])
        page.check("input[name=need_category][value=roof_or_ceiling]")
        page.fill("#id_description", "Final visual confirm test data.")
        page.click(".action-bar button:has-text('Continue')")
        page.wait_for_url("**/request-help/step/home")
        _assert_no_sideways_scroll(page, "R3")
        if mode["text200"]:
            # At 195px "manufactured" is physically wider than the card's text box; wrapping it
            # there is the only alternative to sideways scrolling (WCAG 1.4.10), so R3 is held
            # to "no sideways scroll" at 195px and to "no broken words" at 390 + 200% text.
            _assert_words_on_one_line(
                page, "#id_property_type .choice-card", ["Townhouse", "Apartment", "manufactured"]
            )
        context.close()
        browser.close()


def _session_cookie(live_server, user):
    from django.conf import settings
    from django.test import Client

    client = Client()
    client.force_login(user)
    session = client.session
    session["ham_mfa_satisfied"] = True
    session.save()
    return {
        "name": settings.SESSION_COOKIE_NAME,
        "value": client.cookies[settings.SESSION_COOKIE_NAME].value,
        "url": live_server.url,
    }


def _make_user(email, full_name, role):
    from ham.identity.models import RoleAssignment, SharedIdentityProfile, User
    from ham.platform.clock import now as clock_now

    user = User.objects.create_user(email=email)
    SharedIdentityProfile.objects.create(user=user, full_name=full_name)
    RoleAssignment.objects.create(user=user, role=role, granted_at=clock_now())
    return user


def _make_request(**overrides):
    from ham.authz.context import RequesterContext, SystemContext
    from ham.requests.services import complete_intake_checks, submit_request
    from tests.requests.conftest import make_payload

    req = submit_request(
        RequesterContext(request_id=None),
        draft_id=uuid.uuid4(),
        verification_id=uuid.uuid4(),
        payload=make_payload(**overrides),
    )
    complete_intake_checks(SystemContext(), request_id=req.id)
    return req


def _add_ready_photo(req, *, size=(1600, 900)):
    from PIL import Image

    from ham.authz.context import RequesterContext
    from ham.media import services as media_services
    from ham.media.jobs import process_item
    from ham.media.models import RequestMedia
    from ham.platform.storage import get_object_store

    buf = io.BytesIO()
    Image.new("RGB", size, color="blue").save(buf, format="JPEG")
    data = buf.getvalue()
    ctx = RequesterContext(request_id=req.id)
    reserved = media_services.reserve_uploads(
        ctx, intents=[media_services.UploadIntent("photo", "image/jpeg", len(data))]
    )[0]
    item = RequestMedia.objects.get(id=reserved.item_id)
    get_object_store().put_object(item.quarantine_key, data, content_type="image/jpeg")
    media_services.complete_upload(ctx, item_id=item.id)
    process_item(str(item.id))
    item.refresh_from_db()
    assert item.status == "ready"
    return item


@pytest.mark.parametrize("width", [390, 768, 1280])
def test_media_viewer_fits_the_screen_and_has_a_heading(live_server, width):
    from playwright.sync_api import sync_playwright

    from ham.authz import roles

    director = _make_user("viewer-director@example.org", "Marcus Bell", roles.HAM_DIRECTOR)
    req = _make_request()
    item = _add_ready_photo(req)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": width, "height": 900})
        context.add_cookies([_session_cookie(live_server, director)])
        page = context.new_page()
        page.goto(f"{live_server.url}/requests/{req.id}/media/{item.id}/")
        page.wait_for_selector("img.media-viewer__media")
        page.wait_for_function("document.querySelector('img.media-viewer__media').complete")
        _assert_no_sideways_scroll(page, f"media viewer at {width}")
        assert page.locator("h1").count() == 1
        context.close()
        browser.close()


@pytest.mark.parametrize("mode", _MODES)
def test_pastor_home_reflows_and_every_bottom_nav_tab_is_reachable(live_server, mode):
    from playwright.sync_api import sync_playwright

    from ham.authz import roles

    pastor = _make_user("home-pastor@example.org", "Pastor Ray", roles.PASTOR)
    for _ in range(2):
        _make_request(
            urgent_requested=True, urgency_justification="Water is coming through the ceiling."
        )

    with sync_playwright() as p:
        browser, context, page = _new_page(p, mode)
        context.add_cookies([_session_cookie(live_server, pastor)])
        page.goto(f"{live_server.url}/")
        _assert_no_sideways_scroll(page, "Pastor Home")
        links = page.locator(".nav--bottom .nav__link")
        assert links.count() >= 2
        iw = page.evaluate("window.innerWidth")
        for i in range(links.count()):
            box = links.nth(i).bounding_box()
            assert box is not None and box["width"] > 0
            assert box["x"] + box["width"] <= iw + 1, f"bottom-nav tab {i} is clipped off-screen"
            center = page.evaluate(
                "([x, y]) => document.elementFromPoint(x, y)?.closest('.nav__link') !== null",
                [box["x"] + box["width"] / 2, box["y"] + box["height"] / 2],
            )
            assert center, f"bottom-nav tab {i} can't be hit at its center"
        context.close()
        browser.close()


def test_bottom_nav_labels_stay_visible_on_a_normal_390_phone(live_server):
    """The narrow-bar rule must only kick in when the tabs truly don't fit."""
    from playwright.sync_api import sync_playwright

    from ham.authz import roles

    pastor = _make_user("labels-pastor@example.org", "Pastor Ray", roles.PASTOR)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 390, "height": 844})
        context.add_cookies([_session_cookie(live_server, pastor)])
        page = context.new_page()
        page.goto(f"{live_server.url}/")
        labels = page.locator(".nav--bottom .nav__label")
        assert labels.count() >= 2
        for i in range(labels.count()):
            assert labels.nth(i).bounding_box()["width"] > 1, f"label {i} hidden at 390"
        context.close()
        browser.close()
