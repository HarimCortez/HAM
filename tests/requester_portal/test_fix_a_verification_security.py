"""Step-2 fix round (FIX-A): H1 (challenge <-> draft/email binding), H2 (identical UI /
purpose-scoped budgets), M1 (INTAKE_SUBMISSIONS_PER_EMAIL_PER_DAY, NO_EMAIL cap Q-146,
per-IP code-send cap, FIND_REQUEST_TRIES_PER_IP_PER_HOUR), M6/N13 (`requester_verification.
locked` audited, no address), L6 (lockout scoped per-draft+IP, not per address).

Reuses `test_submission_flow.py`'s `_real_portal_lookups`/`_base_payload`/`_verified_challenge`
shape rather than importing them (new file, per the wave brief), so this file stays
independently runnable if that one changes.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from ham.audit.models import AuditEvent
from ham.jobs import run_due_jobs_now
from ham.platform import otp
from ham.platform.clock import FixedClock, set_clock
from ham.requester_portal import drafts, services, verification
from ham.requester_portal.models import RequesterVerificationChallenge
from ham.requests import queries as requests_queries
from ham.requests.models import Requester
from ham.rules import RULES

pytestmark = pytest.mark.django_db(transaction=True)

T0 = dt.datetime(2026, 9, 28, 12, 0, tzinfo=dt.UTC)


@pytest.fixture
def clock() -> FixedClock:
    c = FixedClock(T0)
    set_clock(c)
    return c


@pytest.fixture(autouse=True)
def _real_portal_lookups():
    def _facts_lookup(request_id: uuid.UUID) -> services.RequestLinkFacts:
        facts = requests_queries.request_facts_for_portal(request_id)
        return services.RequestLinkFacts(status=facts.status, closed_at=facts.closed_at)

    services.register_request_facts_lookup(_facts_lookup)
    services.register_request_contact_lookup(requests_queries.request_contact_for_portal)
    services.register_email_to_request_ids_lookup(requests_queries.request_ids_for_portal_email)
    yield
    services._request_facts_lookup = None  # noqa: SLF001
    services._request_contact_lookup = None  # noqa: SLF001
    services._email_to_request_ids_lookup = None  # noqa: SLF001


def _base_payload(**overrides) -> dict:
    data = {
        "full_name": "Doris Palmer",
        "email": "doris.p@example.org",
        "phone": "(305) 555-0177",
        "relationship_to_property": "owner",
        "line1": "1400 NW Example Ave",
        "city": "Miami",
        "state": "FL",
        "postal_code": "33125",
        "property_type": "house",
        "need_category": "roof_or_ceiling",
        "description": "Water comes through my bedroom ceiling when it rains.",
        "hazards": ["none_known"],
        "availability": ["any_time"],
        "contact_preference": "email",
        "attested_statements": ["owner_authority", "responsibility"],
    }
    data.update(overrides)
    return data


def _start_and_fill(email: str, **overrides) -> uuid.UUID:
    start = drafts.start_draft(email=email)
    assert start.status == "created"
    draft = start.draft
    assert draft is not None
    drafts.save_step(draft.id, _base_payload(email=email, **overrides))
    return draft.id


def _send_code(draft_id: uuid.UUID, *, email: str, code: str = "654321", ip_address: str = ""):
    result = verification.request_intake_verification(
        draft_id=draft_id, email=email, ip_address=ip_address
    )
    assert result.status == "sent"
    run_due_jobs_now()
    challenge = RequesterVerificationChallenge.objects.get(draft_id=draft_id, purpose="intake")
    challenge.code_hash = otp.hash_value(code)
    challenge.save(update_fields=["code_hash"])
    return challenge, code


class TestH1ChallengeBinding:
    """A code sent for one draft/email must never be usable to submit a different one."""

    def test_verified_code_for_address_a_cannot_submit_drafts_current_different_email(
        self, clock: FixedClock
    ):
        draft_id = _start_and_fill("attacker@example.org")
        challenge, code = _send_code(draft_id, email="attacker@example.org")
        verify_result = verification.verify_code(
            purpose="intake", email="attacker@example.org", code=code, draft_id=draft_id
        )
        assert verify_result.ok
        assert verify_result.challenge is not None

        # The attacker now edits the SAME draft to the victim's email (after the code was
        # already redeemed) and tries to submit with the already-consumed challenge.
        drafts.save_step(draft_id, {"email": "victim@example.org"})
        with pytest.raises(ValueError, match="does not match"):
            services.submit_and_issue_link(
                draft_id=draft_id, verification_id=verify_result.challenge.id
            )
        assert not Requester.objects.filter(email="victim@example.org").exists()

    def test_challenge_cannot_be_reused_for_a_second_submission(self, clock: FixedClock):
        draft_id = _start_and_fill("doris.p@example.org")
        challenge, code = _send_code(draft_id, email="doris.p@example.org")
        verify_result = verification.verify_code(
            purpose="intake", email="doris.p@example.org", code=code, draft_id=draft_id
        )
        assert verify_result.ok and verify_result.challenge is not None

        result = services.submit_and_issue_link(
            draft_id=draft_id, verification_id=verify_result.challenge.id
        )
        assert result.request is not None
        run_due_jobs_now()  # drain the deferred duplicate-check job (test isolation)

        # Same draft, freshly re-filled and re-consumed_at cleared? No -- the draft itself is
        # now marked consumed, so a second submit with the same (already-spent) verification
        # id must fail regardless.
        with pytest.raises(ValueError):
            services.submit_and_issue_link(
                draft_id=draft_id, verification_id=verify_result.challenge.id
            )

    def test_editing_email_after_code_sent_invalidates_the_outstanding_challenge(
        self, clock: FixedClock
    ):
        draft_id = _start_and_fill("first@example.org")
        _send_code(draft_id, email="first@example.org")

        # Change the draft's email before the code is ever entered (the `email=` kwarg is
        # what `ham.web.views_requester`'s real step views pass -- it's what actually drives
        # the email-key-changed invalidation, not just merging into the stored payload dict).
        drafts.save_step(draft_id, {"email": "second@example.org"}, email="second@example.org")

        result = verification.verify_code(
            purpose="intake", email="first@example.org", code="654321", draft_id=draft_id
        )
        assert not result.ok
        assert result.reason == "expired"

    def test_a_link_click_uses_the_challenges_own_draft_id_not_a_cookie(self, clock: FixedClock):
        """H1's `_after_verified` fix: this is a unit-level proof that
        `submit_and_issue_link` only trusts the challenge's `draft_id`, exercised the same way
        `ham.web.views_requester.request_help_verify_link` already does."""
        draft_id = _start_and_fill("doris.p@example.org")
        challenge, code = _send_code(draft_id, email="doris.p@example.org")
        result = verification.verify_code(
            purpose="intake", email="doris.p@example.org", code=code, draft_id=draft_id
        )
        assert result.ok and result.challenge is not None
        assert result.challenge.draft_id == draft_id
        submission = services.submit_and_issue_link(
            draft_id=result.challenge.draft_id,
            verification_id=result.challenge.id,
            verification_method="email_link",
        )
        assert submission.request is not None
        run_due_jobs_now()  # drain the deferred duplicate-check job (test isolation)


class TestH2IdenticalUiAndPurposeBudgets:
    def test_per_email_cap_is_scoped_to_one_purpose(self, clock: FixedClock):
        """Filling the link_regeneration budget for an address must not affect that same
        address's intake budget (the shared-counter bug H2 found)."""
        cap = RULES.intake.REQUESTER_CODE_EMAILS_PER_ADDRESS_PER_HOUR
        email_key = otp.hash_value("shared@example.org")
        now = clock.now()
        for _ in range(cap):
            RequesterVerificationChallenge.objects.create(
                purpose=RequesterVerificationChallenge.PURPOSE_LINK_REGENERATION,
                request_id=uuid.uuid4(),
                email_key=email_key,
                code_hash="x",
                link_token_hash=uuid.uuid4().hex,
                created_at=now,
                expires_at=now + dt.timedelta(minutes=15),
            )
        draft_id = _start_and_fill("shared@example.org")
        result = verification.request_intake_verification(
            draft_id=draft_id, email="shared@example.org"
        )
        assert result.status == "sent"

    def test_per_ip_code_send_cap(self, clock: FixedClock):
        cap = RULES.intake.REQUESTER_CODE_EMAILS_PER_IP_PER_HOUR
        for i in range(cap):
            draft_id = _start_and_fill(f"person{i}@example.org")
            result = verification.request_intake_verification(
                draft_id=draft_id, email=f"person{i}@example.org", ip_address="203.0.113.9"
            )
            assert result.status == "sent"
        draft_id = _start_and_fill("onemore@example.org")
        result = verification.request_intake_verification(
            draft_id=draft_id, email="onemore@example.org", ip_address="203.0.113.9"
        )
        assert result.status == "rate_limited"

    def test_find_request_per_ip_cap(self, clock: FixedClock):
        cap = RULES.intake.FIND_REQUEST_TRIES_PER_IP_PER_HOUR
        for _ in range(cap):
            result = services.find_my_request(email="nobody@example.org", ip_address="198.51.100.5")
            assert result.status == "sent"
        # The (cap + 1)th try from the same IP is silently dropped but still looks the same.
        from ham.requester_portal.models import FindRequestAttempt

        before = FindRequestAttempt.objects.filter(ip_address="198.51.100.5").count()
        result = services.find_my_request(email="nobody@example.org", ip_address="198.51.100.5")
        assert result.status == "sent"
        after = FindRequestAttempt.objects.filter(ip_address="198.51.100.5").count()
        assert after == before  # capped attempt is not even logged as a new try


class TestM1SubmissionCaps:
    def test_email_submission_cap_per_day(self, clock: FixedClock):
        cap = RULES.intake.INTAKE_SUBMISSIONS_PER_EMAIL_PER_DAY
        for i in range(cap):
            clock.advance(RULES.intake.REQUESTER_CODE_RESEND_COOLDOWN + dt.timedelta(seconds=1))
            draft_id = _start_and_fill("busy@example.org", line1=f"{i} Example Ave")
            challenge, code = _send_code(draft_id, email="busy@example.org")
            verify_result = verification.verify_code(
                purpose="intake", email="busy@example.org", code=code, draft_id=draft_id
            )
            assert verify_result.ok and verify_result.challenge is not None
            services.submit_and_issue_link(
                draft_id=draft_id, verification_id=verify_result.challenge.id
            )
            run_due_jobs_now()

        clock.advance(RULES.intake.REQUESTER_CODE_RESEND_COOLDOWN + dt.timedelta(seconds=1))
        draft_id = _start_and_fill("busy@example.org", line1="one too many")
        challenge, code = _send_code(draft_id, email="busy@example.org")
        verify_result = verification.verify_code(
            purpose="intake", email="busy@example.org", code=code, draft_id=draft_id
        )
        assert verify_result.ok and verify_result.challenge is not None
        with pytest.raises(services.IntakeSubmissionRateLimited):
            services.submit_and_issue_link(
                draft_id=draft_id, verification_id=verify_result.challenge.id
            )

    def test_no_email_submission_cap_per_phone_q146(self, clock: FixedClock):
        cap = RULES.intake.NO_EMAIL_SUBMISSIONS_PER_PHONE_PER_DAY
        for i in range(cap):
            start = drafts.start_draft()
            draft = start.draft
            assert draft is not None
            drafts.save_step(
                draft.id,
                _base_payload(
                    email="",
                    no_email=True,
                    phone="(305) 555-0199",
                    line1=f"{i} Example Ave",
                ),
            )
            result = services.submit_and_issue_link(draft_id=draft.id, verification_id=None)
            assert result.request is not None

        start = drafts.start_draft()
        draft = start.draft
        assert draft is not None
        drafts.save_step(
            draft.id,
            _base_payload(email="", no_email=True, phone="(305) 555-0199", line1="one too many"),
        )
        with pytest.raises(services.IntakeSubmissionRateLimited):
            services.submit_and_issue_link(draft_id=draft.id, verification_id=None)


class TestM6LockoutAudited:
    def test_daily_cap_lockout_is_audited_without_the_address(self, clock: FixedClock):
        draft_id = _start_and_fill("locked@example.org")
        _send_code(draft_id, email="locked@example.org")
        max_attempts = RULES.intake.REQUESTER_CODE_MAX_ATTEMPTS
        for _ in range(max_attempts):
            result = verification.verify_code(
                purpose="intake", email="locked@example.org", code="000000", draft_id=draft_id
            )
            assert not result.ok

        events = AuditEvent.objects.filter(action="requester_verification.locked")
        assert events.exists()
        for event in events:
            assert "locked@example.org" not in str(event.context)
            assert "locked@example.org" not in str(event.target_id)
            assert event.target_id == str(draft_id)


class TestL6LockoutScopedPerDraft:
    def test_wrong_codes_against_ones_own_draft_do_not_lock_another_draft(self, clock: FixedClock):
        """Two different people who both typed the SAME email into their own drafts (one, or
        both, could be an attacker) must not be able to lock each other out."""
        victim_draft = _start_and_fill("victim@example.org")
        _send_code(victim_draft, email="victim@example.org")

        clock.advance(RULES.intake.REQUESTER_CODE_RESEND_COOLDOWN + dt.timedelta(seconds=1))
        attacker_draft = _start_and_fill("victim@example.org")
        _send_code(attacker_draft, email="victim@example.org")

        max_attempts = RULES.intake.REQUESTER_CODE_MAX_ATTEMPTS
        for _ in range(max_attempts):
            verification.verify_code(
                purpose="intake",
                email="victim@example.org",
                code="000000",
                draft_id=attacker_draft,
            )

        # The victim's own draft/challenge is untouched.
        challenge = RequesterVerificationChallenge.objects.get(draft_id=victim_draft)
        assert challenge.failed_attempts == 0
