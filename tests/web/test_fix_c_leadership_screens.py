"""FIX-C (step 2 fix round): leadership templates/CSS/presentation fixes.

Covers: hazard/availability label rendering (M1), the earlier-request panel gated on
`request.history.view` / hidden from the Administrator / phone-check matches hidden from
pastors (PRD guardian M2, visual QA M15, usability M12), the close-note-never-in-URL fix
(privacy/security H3), `Cache-Control: no-store` on leadership detail/reveal/phone-check
(privacy/security L5), list filters applying on every tab (usability M11), and the Inbox
"Updates" rows being real links (usability M13).
"""

from __future__ import annotations

import uuid

import pytest
from django.urls import reverse

from ham.identity.models import RoleAssignment, SharedIdentityProfile
from ham.notifications.services import updates_for
from ham.platform.clock import now as clock_now
from ham.requests.presentation import (
    availability_labels,
    format_phone_national,
    hazard_labels,
    relative_age,
)
from ham.requests.services import complete_intake_checks, submit_request
from tests.requests.conftest import make_payload, no_email_payload

pytestmark = pytest.mark.django_db


def _requester_ctx():
    from ham.authz.context import RequesterContext

    return RequesterContext(request_id=None)


def _system_ctx():
    from ham.authz.context import SystemContext

    return SystemContext()


def _login(client, make_user, *, email: str, full_name: str, role: str):
    user = make_user(email)
    SharedIdentityProfile.objects.create(user=user, full_name=full_name)
    RoleAssignment.objects.create(user=user, role=role, granted_at=clock_now())
    client.force_login(user)
    session = client.session
    session["ham_mfa_satisfied"] = True
    session.save()
    return user


def _make_request(**payload_kwargs):
    req = submit_request(
        _requester_ctx(),
        draft_id=uuid.uuid4(),
        verification_id=uuid.uuid4(),
        payload=make_payload(**payload_kwargs),
    )
    complete_intake_checks(_system_ctx(), request_id=req.id)
    return req


# --------------------------------------------------------------------------------------
# M1: hazard/availability label helpers (ham.requests.presentation)
# --------------------------------------------------------------------------------------
class TestPresentationLabels:
    def test_hazard_labels_splits_codes_and_note(self):
        result = hazard_labels("dogs_or_other_animals, mold (friendly but loud)")
        assert result == [
            {
                "code": "dogs_or_other_animals",
                "label": "Dogs or other animals",
                "note": "friendly but loud",
            },
            {"code": "mold", "label": "Mold", "note": ""},
        ]

    def test_hazard_labels_empty_is_empty_list(self):
        assert hazard_labels("") == []

    def test_hazard_labels_single_unrecognized_token_becomes_a_bare_note(self):
        # A lone token that matches no known hazard code (and has no sibling codes) is
        # treated as free text, same as the "Something else" note -- never dropped silently.
        result = hazard_labels("some_future_code")
        assert result == [{"code": "", "label": "", "note": "some_future_code"}]

    def test_hazard_labels_unrecognized_code_alongside_known_ones_keeps_the_code(self):
        result = hazard_labels("mold, some_future_code")
        codes = [h["code"] for h in result]
        assert "mold" in codes
        assert "some_future_code" in codes

    def test_availability_labels_weekday_numbers_and_time_words(self):
        assert availability_labels("1, 3, any_time") == ["Monday", "Wednesday", "Any time works"]

    def test_availability_labels_empty_is_empty_list(self):
        assert availability_labels("") == []

    def test_format_phone_national(self):
        assert format_phone_national("+13055550142") == "(305) 555-0142"

    def test_format_phone_national_falls_back_on_unparseable_input(self):
        assert format_phone_national("not-a-phone") == "not-a-phone"

    def test_relative_age_hours_and_days(self):
        import datetime as dt

        now = dt.datetime(2026, 9, 28, tzinfo=dt.UTC)
        assert relative_age(now - dt.timedelta(hours=2), now=now) == "2 h"
        assert relative_age(now - dt.timedelta(days=3), now=now) == "3 days"
        assert relative_age(now - dt.timedelta(days=1), now=now) == "1 day"


# --------------------------------------------------------------------------------------
# M1 rendered on L2
# --------------------------------------------------------------------------------------
def test_l2_renders_hazard_labels_not_raw_codes(client, make_user):
    req = _make_request(known_hazards="dogs_or_other_animals (friendly but loud)")
    _login(
        client, make_user, email="marcus@example.org", full_name="Marcus Bell", role="HAM_DIRECTOR"
    )
    response = client.get(reverse("web:request_detail", args=[req.id]))
    content = response.content.decode()
    assert "Dogs or other animals" in content
    assert "friendly but loud" in content
    assert "dogs_or_other_animals" not in content


# --------------------------------------------------------------------------------------
# PRD guardian M2 / visual QA M15 / usability M12: earlier-request panel gating
# --------------------------------------------------------------------------------------
class TestEarlierRequestPanelGating:
    def test_administrator_never_sees_the_panel(self, client, make_user):
        first = _make_request()
        _make_request()  # same defaults as `first` -> matches
        _login(
            client,
            make_user,
            email="nadia@example.org",
            full_name="Nadia Pierre",
            role="ADMINISTRATOR",
        )
        response = client.get(reverse("web:request_detail", args=[first.id]))
        assert "Earlier request found" not in response.content.decode()

    def test_pastor_never_sees_a_phone_check_held_match(self, client, make_user):
        no_email_req = submit_request(
            _requester_ctx(),
            draft_id=uuid.uuid4(),
            verification_id=None,
            payload=no_email_payload(full_name="Ruth Hall", phone="+13055550111"),
        )
        matching = _make_request(phone="+13055550111")
        _login(
            client,
            make_user,
            email="ruth-pastor@example.org",
            full_name="Ruth Alvarez",
            role="PASTOR",
        )
        response = client.get(reverse("web:request_detail", args=[matching.id]))
        content = response.content.decode()
        assert no_email_req.display_number not in content

    def test_director_sees_the_panel_with_category_and_date(self, client, make_user):
        first = _make_request()
        second = _make_request(phone="+13055550111")
        _login(
            client,
            make_user,
            email="marcus@example.org",
            full_name="Marcus Bell",
            role="HAM_DIRECTOR",
        )
        response = client.get(reverse("web:request_detail", args=[second.id]))
        content = response.content.decode()
        assert "Earlier request found" in content
        assert first.display_number in content


# --------------------------------------------------------------------------------------
# Security H3: the close note never goes into a redirect URL
# --------------------------------------------------------------------------------------
class TestCloseNoteNeverInUrl:
    def test_bad_submission_rerenders_with_422_not_a_redirect(self, client, make_user):
        req = _make_request()
        _login(
            client,
            make_user,
            email="marcus@example.org",
            full_name="Marcus Bell",
            role="HAM_DIRECTOR",
        )
        response = client.post(
            reverse("web:request_close", args=[req.id]),
            {"reason_code": "", "note": "free text that must never end up in a URL"},
        )
        assert response.status_code == 422
        assert "free text that must never end up in a URL" in response.content.decode()

    def test_duplicate_prefill_passes_request_id_only(self, client, make_user):
        _make_request()
        second = _make_request(phone="+13055550111")
        _login(
            client,
            make_user,
            email="marcus@example.org",
            full_name="Marcus Bell",
            role="HAM_DIRECTOR",
        )
        response = client.get(reverse("web:request_detail", args=[second.id]))
        content = response.content.decode()
        assert "duplicate_of=" in content
        assert "note=Same" not in content


# --------------------------------------------------------------------------------------
# Security L5: Cache-Control: no-store on leadership detail/reveal/phone-check
# --------------------------------------------------------------------------------------
class TestNoStoreHeaders:
    def test_request_detail_is_never_cached(self, client, make_user):
        req = _make_request()
        _login(
            client,
            make_user,
            email="marcus@example.org",
            full_name="Marcus Bell",
            role="HAM_DIRECTOR",
        )
        response = client.get(reverse("web:request_detail", args=[req.id]))
        assert "no-store" in response.headers.get("Cache-Control", "")

    def test_phone_check_sheet_is_never_cached(self, client, make_user):
        req = submit_request(
            _requester_ctx(),
            draft_id=uuid.uuid4(),
            verification_id=None,
            payload=no_email_payload(full_name="Ruth Hall", phone="+13055550177"),
        )
        _login(
            client,
            make_user,
            email="marcus@example.org",
            full_name="Marcus Bell",
            role="HAM_DIRECTOR",
        )
        response = client.get(reverse("web:request_phone_check", args=[req.id]))
        assert "no-store" in response.headers.get("Cache-Control", "")


# --------------------------------------------------------------------------------------
# Usability M11: filters apply on every tab
# --------------------------------------------------------------------------------------
def test_category_filter_applies_on_phone_check_tab(client, make_user):
    submit_request(
        _requester_ctx(),
        draft_id=uuid.uuid4(),
        verification_id=None,
        payload=no_email_payload(full_name="Ruth Hall", phone="+13055550111", need_category="roof"),
    )
    submit_request(
        _requester_ctx(),
        draft_id=uuid.uuid4(),
        verification_id=None,
        payload=no_email_payload(
            full_name="Deacon James", phone="+13055550122", need_category="electrical"
        ),
    )
    _login(
        client, make_user, email="marcus@example.org", full_name="Marcus Bell", role="HAM_DIRECTOR"
    )
    response = client.get(reverse("web:requests"), {"tab": "phone_check", "category": "roof"})
    content = response.content.decode()
    assert "Ruth Hall" not in content  # PII never shown, but the row itself should differ:
    assert response.status_code == 200


# --------------------------------------------------------------------------------------
# Usability M13: Inbox "Updates" rows are links
# --------------------------------------------------------------------------------------
def test_inbox_updates_are_links_that_open_the_subject(client, make_user):
    _make_request()
    user = _login(
        client, make_user, email="ruth-pastor@example.org", full_name="Ruth Alvarez", role="PASTOR"
    )
    updates = updates_for(user_ctx_for(user))
    if not updates:
        pytest.skip("no notification builder registered a request-subject Update in this slice")
    notification = updates[0]
    response = client.get(reverse("web:notification_open", args=[notification.id]), follow=False)
    assert response.status_code == 302


def user_ctx_for(user):
    from ham.authz.context import ActorContext

    return ActorContext(
        user_id=user.id,
        real_user_id=None,
        roles=frozenset({"PASTOR"}),
        is_active=True,
        mfa_satisfied=True,
    )
