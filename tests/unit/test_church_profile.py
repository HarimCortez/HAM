from __future__ import annotations

import pytest

from ham.platform.brand import BrandConfigError, load_brand
from ham.platform.church import church_profile
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
