"""FIX-G NH1 (High): "already received" must never reveal the HAM # or a path to the secure
page to a browser that hasn't itself proven anything for this request. A session that still
names an already-submitted draft id is not proof -- only a correct code entered on THIS
browser, or a link consumed by THIS browser, counts.

Regression test derived from the security reviewer's PoC
(``scratchpad/poc3/test_poc_reveal.py``): submit from device A via the emailed link; back on
the original browser (whose session still holds the draft's pending code-entry state), POST a
garbage code. Before the fix: this revealed the HAM # and a direct
``/request-help/r/<token>`` link, straight from a stale session with no correct code entered.
After the fix: neutral message only, and the verify session is spent.
"""

from __future__ import annotations

import re

import pytest
from django.core import mail
from django.test import Client
from django.urls import reverse

from ham.jobs import run_due_jobs_now
from tests.web.test_requester_portal_screens import _fill_wizard

pytestmark = pytest.mark.django_db(transaction=True)

_LINK_RE = re.compile(r"/request-help/verify/link/([^\s]+)")
_SECURE_HREF_RE = re.compile(r'href="(/request-help/r/[^"]+)"')


def test_garbage_code_on_the_original_session_never_reveals_ham_number_or_secure_link():
    original = Client(REMOTE_ADDR="10.1.1.1")
    _fill_wizard(original)
    mail.outbox.clear()
    resp = original.post(
        reverse("web:request_help_step", kwargs={"step": "review"}),
        {"attested_statements": ["owner_authority", "responsibility"]},
        follow=True,
    )
    assert resp.status_code == 200, resp.content
    run_due_jobs_now()
    assert len(mail.outbox) == 1
    match = _LINK_RE.search(str(mail.outbox[0].body))
    assert match is not None
    token = match.group(1)

    # Device A (a different browser -- e.g. the phone the email was actually read on) opens
    # the emailed link and submits the request first.
    device_a = Client(REMOTE_ADDR="10.2.2.2")
    submit_resp = device_a.post(
        reverse("web:request_help_verify_link", kwargs={"token": token}), follow=True
    )
    assert submit_resp.status_code == 200
    assert b"HAM #" in submit_resp.content
    run_due_jobs_now()

    # Back on the ORIGINAL browser: its session still names this draft's pending code entry
    # (`ham_intake_verify`), but this POST's own code is wrong -- nothing was just proven on
    # this browser. Holding a session that merely *names* an already-submitted draft is not
    # proof of anything.
    garbage_resp = original.post(reverse("web:request_help_verify"), {"code": "000000"})
    assert garbage_resp.status_code == 200
    html = garbage_resp.content.decode()

    assert "HAM #" not in html
    assert _SECURE_HREF_RE.search(html) is None
    assert "Already received" in html
    assert "please start again" not in html.lower()

    # The verify session is spent -- a second identical POST behaves the same way (a normal
    # "start again" redirect, never a 500 from a half-cleared session), and still reveals
    # nothing.
    again = original.post(reverse("web:request_help_verify"), {"code": "000000"})
    assert again.status_code in (200, 302)
    assert b"HAM #" not in again.content
