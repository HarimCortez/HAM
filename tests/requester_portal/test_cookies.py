from __future__ import annotations

import uuid

from django.http import HttpResponse
from django.test import RequestFactory

from ham.requester_portal.cookies import (
    COOKIE_NAME,
    clear_resume_cookie,
    read_resume_draft_id,
    set_resume_cookie,
)


def _cookie_value(response: HttpResponse) -> str:
    return response.cookies[COOKIE_NAME].value


def test_set_and_read_resume_cookie():
    draft_id = uuid.uuid4()
    response = HttpResponse()
    set_resume_cookie(response, draft_id=draft_id)
    cookie = response.cookies[COOKIE_NAME]
    assert cookie["httponly"]
    assert cookie["samesite"] == "Lax"

    request = RequestFactory().get("/")
    request.COOKIES[COOKIE_NAME] = _cookie_value(response)
    assert read_resume_draft_id(request) == draft_id


def test_resume_cookie_is_browser_scoped_not_a_global_lookup():
    """A resume cookie only resolves via the cookie itself (the only thing a "same browser"
    check can mean for a plain HTTP request) — a request with no cookie at all, or a forged
    one, never resolves to a draft id (Q-139)."""
    request = RequestFactory().get("/")
    assert read_resume_draft_id(request) is None

    request2 = RequestFactory().get("/")
    request2.COOKIES[COOKIE_NAME] = "not-a-valid-signed-value"
    assert read_resume_draft_id(request2) is None


def test_clear_resume_cookie():
    response = HttpResponse()
    clear_resume_cookie(response)
    assert response.cookies[COOKIE_NAME].value == ""
