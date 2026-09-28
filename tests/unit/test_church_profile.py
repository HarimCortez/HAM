from __future__ import annotations

import datetime as dt

import pytest

from ham.platform.brand import BrandConfigError, load_brand
from ham.platform.church import church_profile, format_church_time, is_valid_time_zone
from ham.platform.models import ChurchProfile


@pytest.mark.django_db
def test_church_profile_merges_brand_and_db_row(settings):
    settings.HAM_BRAND = "miami-temple"
    load_brand.cache_clear()
    row = ChurchProfile.get_solo()
    row.ham_phone = "+1 305 555 0100"
    row.ham_email = "office@example.org"
    row.time_zone = "America/New_York"
    row.website_url = "https://example.org"
    row.save()

    view = church_profile()

    assert view.name  # from brand.json
    assert view.phone == "+1 305 555 0100"
    assert view.email == "office@example.org"
    assert view.time_zone == "America/New_York"


@pytest.mark.django_db
def test_church_profile_is_a_singleton():
    first = ChurchProfile.get_solo()
    second = ChurchProfile.get_solo()
    assert first.pk == second.pk
    assert ChurchProfile.objects.count() == 1


def test_load_brand_raises_clear_error_for_unknown_brand():
    load_brand.cache_clear()
    with pytest.raises(BrandConfigError):
        load_brand("does-not-exist")


class TestTimeZoneHelpers:
    """Q-030/§70.5: one church time zone, validated and labeled with its abbreviation."""

    def test_valid_iana_zone(self):
        assert is_valid_time_zone("America/New_York") is True

    def test_invalid_zone_rejected(self):
        assert is_valid_time_zone("Not/AZone") is False
        assert is_valid_time_zone("") is False

    def test_format_church_time_uses_zone_abbreviation(self, settings, db):
        settings.HAM_BRAND = "miami-temple"
        load_brand.cache_clear()
        row = ChurchProfile.get_solo()
        row.time_zone = "America/New_York"
        row.save()
        moment = dt.datetime(2026, 1, 15, 17, 0, tzinfo=dt.UTC)  # winter -> EST
        rendered = format_church_time(moment)
        assert "EST" in rendered
        assert "12:00" in rendered  # UTC-5
