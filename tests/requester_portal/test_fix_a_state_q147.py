"""Step-2 fix round (FIX-A) Q-147: R3's state is validated against the real 50-states-+-DC
list (not just "any 2 characters") and is prefilled from the church's own state when set.
"""

from __future__ import annotations

import pytest
from django.test import Client

from ham.platform.church import US_STATE_CODES, church_profile, is_valid_us_state
from ham.platform.models import ChurchProfile


def test_is_valid_us_state():
    assert is_valid_us_state("FL")
    assert is_valid_us_state("fl")
    assert not is_valid_us_state("ZZ")
    assert not is_valid_us_state("")
    assert len(US_STATE_CODES) == 51  # 50 states + DC


@pytest.mark.django_db
def test_church_profile_state_defaults_blank():
    assert church_profile().state == ""


@pytest.mark.django_db
def test_r3_prefills_state_from_church_profile():
    profile = ChurchProfile.get_solo()
    profile.state = "FL"
    profile.save(update_fields=["state"])

    client = Client()
    start = client.post("/request-help/begin")
    assert start.status_code == 302
    response = client.get("/request-help/step/home")
    assert response.status_code == 200
    assert response.context["payload"]["state"] == "FL"


@pytest.mark.django_db
def test_form_rejects_a_non_state_code():
    from ham.platform.church import church_profile
    from ham.requester_portal.forms import validate_intake_payload

    data = {"state": "ZZ"}
    _cleaned, errors = validate_intake_payload(data, church=church_profile())
    assert "state" in errors
