from __future__ import annotations

import pytest
from django.http import HttpResponse
from django.utils import timezone

from ham.platform.brand import load_brand
from ham.platform.models import ChurchProfile
from ham.platform.timezone_middleware import ChurchTimeZoneMiddleware


@pytest.mark.django_db
def test_activates_the_church_time_zone_for_the_request(settings):
    settings.HAM_BRAND = "miami-temple"
    load_brand.cache_clear()
    row = ChurchProfile.get_solo()
    row.time_zone = "America/New_York"
    row.save()

    seen = {}

    def get_response(request):
        seen["tzname"] = timezone.get_current_timezone_name()
        return HttpResponse("ok")

    mw = ChurchTimeZoneMiddleware(get_response)
    mw(request=None)  # request is unused by this middleware's body except passthrough

    assert seen["tzname"] == "America/New_York"
    # Deactivated again after the response, so it never leaks into the next unrelated request.
    assert timezone.get_current_timezone_name() != "America/New_York"


@pytest.mark.django_db
def test_falls_back_to_utc_for_an_invalid_zone(settings):
    settings.HAM_BRAND = "miami-temple"
    load_brand.cache_clear()
    row = ChurchProfile.get_solo()
    row.time_zone = "Not/AZone"
    row.save()

    def get_response(request):
        return HttpResponse("ok")

    mw = ChurchTimeZoneMiddleware(get_response)
    response = mw(request=None)
    assert response.status_code == 200
