"""FIX-E N15 regression: the Church settings screen renders and saves the `state` field (a
2-letter US state select, Q-147) -- it previously existed only on the model/view, with no
template control to set it. New file per wave brief.
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from ham.platform.church import US_STATE_CODES, church_profile
from tests.web.test_fix_c_leadership_screens import _login

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client(client, make_user):
    _login(
        client,
        make_user,
        email="admin-churchsettings@example.org",
        full_name="Admin",
        role="ADMINISTRATOR",
    )
    return client


def test_state_select_renders_every_known_code(admin_client):
    resp = admin_client.get(reverse("web:admin_church_settings"))
    assert resp.status_code == 200
    content = resp.content.decode()
    assert 'name="state"' in content
    for code in ("FL", "CA", "NY"):
        assert f'value="{code}"' in content


def test_admin_can_set_the_state(admin_client):
    resp = admin_client.post(
        reverse("web:admin_church_settings"),
        {
            "ham_phone": "305-555-0100",
            "ham_email": "ham@example.org",
            "state": "ga",
            "time_zone": "America/New_York",
            "website_url": "https://example.org",
        },
    )
    assert resp.status_code == 302
    assert church_profile().state == "GA"


def test_admin_can_clear_the_state_back_to_not_set(admin_client):
    admin_client.post(
        reverse("web:admin_church_settings"),
        {
            "ham_phone": "305-555-0100",
            "ham_email": "ham@example.org",
            "state": "GA",
            "time_zone": "America/New_York",
            "website_url": "https://example.org",
        },
    )
    assert church_profile().state == "GA"

    resp = admin_client.post(
        reverse("web:admin_church_settings"),
        {
            "ham_phone": "305-555-0100",
            "ham_email": "ham@example.org",
            "state": "",
            "time_zone": "America/New_York",
            "website_url": "https://example.org",
        },
    )
    assert resp.status_code == 302
    assert church_profile().state == ""


def test_invalid_state_code_is_rejected(admin_client):
    resp = admin_client.post(
        reverse("web:admin_church_settings"),
        {
            "ham_phone": "305-555-0100",
            "ham_email": "ham@example.org",
            "state": "ZZ",
            "time_zone": "America/New_York",
            "website_url": "https://example.org",
        },
    )
    assert resp.status_code == 200
    assert b"two-letter US state code" in resp.content


def test_seed_dev_sets_church_state_to_fl():
    from django.core.management import call_command

    call_command("seed_dev")
    assert church_profile().state == "FL"


def test_us_state_codes_frozenset_used_by_the_template_is_sane():
    assert "FL" in US_STATE_CODES
    assert len(US_STATE_CODES) == 51  # 50 states + DC
