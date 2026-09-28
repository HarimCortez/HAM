"""Activates the one church time zone for every request (Q-030, PRD §70.5: "one church time
zone in the church profile ... used everywhere").

Placed after ``ham.identity.middleware.SessionLifetimeMiddleware`` and before the route guard
in ``config/settings/base.py``'s ``MIDDLEWARE`` — it doesn't need ``request.actor``, but it
must run before any view (including public ones like ``/sign-in``) so templates and views that
call ``django.utils.timezone.localtime()`` always render in church-local time, never server
(UTC) or browser time. Never depends on the signed-in person: HAM has one church time zone in
V1 (Q-030), not one per user.
"""

from __future__ import annotations

import zoneinfo
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from ham.platform.church import church_profile


class ChurchTimeZoneMiddleware:
    def __init__(self, get_response: Callable) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        tzname = church_profile().time_zone
        try:
            timezone.activate(zoneinfo.ZoneInfo(tzname))
        except zoneinfo.ZoneInfoNotFoundError:  # pragma: no cover - defensive; validated on save
            timezone.deactivate()
        try:
            return self.get_response(request)
        finally:
            timezone.deactivate()
