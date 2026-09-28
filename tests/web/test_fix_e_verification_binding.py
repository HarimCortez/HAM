"""FIX-E N3 regression: `ham.requester_portal.verification.verify_code` must select the
challenge by `draft_id` (intake) or `request_id` (link regeneration), never by email alone --
turned from the security re-check PoC (``test_poc_cross_draft.py``) into a real regression
test. New file per wave brief.

Before the fix: an attacker who types a victim's real email into their *own* draft (the same
draft-owner, not the victim) could burn the victim's real challenge's wrong-attempt budget,
since `verify_code` picked "the most recent, unconsumed challenge for this email+purpose" --
which is always the victim's, because the resend cooldown blocks a second challenge being
created for the same email+purpose while the victim's is still live. That locked the victim
out of entering their own, correct code.

Uses plain `pytest.mark.django_db` (the PoC's `django_db(transaction=True)` was not needed for
two separate `Client()` instances sharing one connection-backed test transaction, and left the
job queue in a state that broke an unrelated, later-run test in the same file order --
`TransactionTestCase`'s real commit + truncate cycle doesn't compose cleanly with
`ham.jobs.run_due_jobs_now()` used elsewhere in this test module).
"""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse

from ham.platform import otp
from ham.requester_portal.models import RequesterVerificationChallenge
from ham.rules import RULES
from tests.web.test_requester_portal_screens import _fill_wizard

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _real(real_portal_lookups):
    pass


def _to_review(c: Client, ip: str) -> None:
    _fill_wizard(c)
    c.post(
        reverse("web:request_help_step", kwargs={"step": "review"}),
        {"attested_statements": ["owner_authority", "responsibility"]},
        REMOTE_ADDR=ip,
    )


def test_attacker_cannot_burn_the_victims_own_challenge():
    victim, attacker = Client(REMOTE_ADDR="10.0.0.1"), Client(REMOTE_ADDR="10.0.0.2")
    _to_review(victim, "10.0.0.1")  # code sent to the shared address for victim's draft
    cv = RequesterVerificationChallenge.objects.get(purpose="intake")
    cv.code_hash = otp.hash_value("111222")
    cv.save(update_fields=["code_hash"])
    victim_failed_attempts_before = cv.failed_attempts

    # Same email typed into a second, unrelated draft -- the resend cooldown means no second
    # challenge row gets created, so before the fix this attacker's draft had no challenge of
    # its own to guess against and verify_code fell back to "the most recent one for this
    # email", i.e. the victim's.
    _to_review(attacker, "10.0.0.2")
    assert RequesterVerificationChallenge.objects.filter(purpose="intake").count() == 1

    for _ in range(RULES.intake.REQUESTER_CODE_MAX_ATTEMPTS):
        resp = attacker.post(
            reverse("web:request_help_verify"), {"code": "000000"}, REMOTE_ADDR="10.0.0.2"
        )
        assert resp.status_code in (302, 422)

    cv.refresh_from_db()
    # N3 fix: the attacker's wrong guesses never touch the victim's challenge -- it belongs to
    # a different draft_id than the attacker's session claims.
    assert cv.failed_attempts == victim_failed_attempts_before

    # The victim can still enter their own, correct code afterwards.
    r = victim.post(reverse("web:request_help_verify"), {"code": "111222"}, REMOTE_ADDR="10.0.0.1")
    assert r.status_code == 302
    cv.refresh_from_db()
    assert cv.consumed_at is not None


def test_attacker_has_no_challenge_to_guess_against_at_all():
    """The attacker's own draft never got a challenge row of its own (cooldown blocked a
    second send for the shared email+purpose) -- `verify_code` must report "no_challenge" for
    it, not silently fall through to someone else's row."""
    victim, attacker = Client(REMOTE_ADDR="10.0.0.3"), Client(REMOTE_ADDR="10.0.0.4")
    _to_review(victim, "10.0.0.3")
    _to_review(attacker, "10.0.0.4")

    resp = attacker.post(
        reverse("web:request_help_verify"), {"code": "999999"}, REMOTE_ADDR="10.0.0.4"
    )
    assert resp.status_code == 422
    assert b"couldn" in resp.content.lower() or b"start again" in resp.content.lower()
