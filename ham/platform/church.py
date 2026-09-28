"""`church_profile()` — the one read-only object templates and other modules use for church
identity (foundation.md §2.2). Merges the deploy-time brand layer with the Admin-editable
`ChurchProfile` row. Templates use `{church.*}` only; never a literal church name/phone/email
anywhere else (CLAUDE.md, design-system/brands/README.md).
"""

from __future__ import annotations

import datetime as dt
import zoneinfo
from dataclasses import dataclass

from ham.platform.brand import Brand, load_brand


@dataclass(frozen=True)
class ChurchProfileView:
    name: str
    short_name: str
    mission_line: str
    display_font: str
    ui_font: str
    logo_on_dark: str
    logo_on_light: str
    logo_mark: str
    logo_alt: str
    phone: str
    email: str
    # Q-147 (decided): the church's own 2-letter USPS state code, used to prefill R3's "The
    # home" step ("Florida · Change") -- "" means not set yet (Admin hasn't filled it in).
    state: str
    time_zone: str
    website_url: str
    # Q-112 (intake.md §8): ISO weekday numbers (1=Monday..7=Sunday) HAM serves requesters on;
    # read by `ham.requester_portal.forms` for the public intake form's availability choices.
    serves_days: tuple[int, ...]


def church_profile() -> ChurchProfileView:
    from ham.platform.models import ChurchProfile  # local import: avoid app-loading races

    brand: Brand = load_brand()
    row = ChurchProfile.get_solo()
    return ChurchProfileView(
        name=brand.name,
        short_name=brand.short_name,
        mission_line=brand.mission_line,
        display_font=brand.display_font,
        ui_font=brand.ui_font,
        logo_on_dark=brand.logo_on_dark,
        logo_on_light=brand.logo_on_light,
        logo_mark=brand.logo_mark,
        logo_alt=brand.logo_alt,
        phone=row.ham_phone,
        email=row.ham_email,
        state=row.state,
        time_zone=row.time_zone,
        website_url=row.website_url,
        serves_days=tuple(row.serves_days),
    )


def is_valid_time_zone(name: str) -> bool:
    """Q-030/§70.5: the church profile's time zone must be a real IANA zone name."""
    return bool(name) and name in zoneinfo.available_timezones()


# Q-147: the 50 states + DC, USPS 2-letter codes -- used both to validate the church profile's
# own `state` field and the public intake form's R3 "The home" address state (`ham.requester_
# portal.forms`). Not a `ham.rules` value (no timedelta/limit/weight, CLAUDE.md), a fixed
# reference vocabulary, same reasoning as `ham.requester_portal.choices`.
US_STATE_CODES: frozenset[str] = frozenset(
    {
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "DC",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
    }
)


def is_valid_us_state(code: str) -> bool:
    return bool(code) and code.strip().upper() in US_STATE_CODES


def format_church_time(moment: dt.datetime, *, church: ChurchProfileView | None = None) -> str:
    """Render a UTC ``moment`` in the church's local time zone with its abbreviation (Q-030,
    §70.5: "label times with the zone abbreviation where shown"), e.g. "3:45 PM EST"."""
    church = church or church_profile()
    try:
        zone = zoneinfo.ZoneInfo(church.time_zone)
    except zoneinfo.ZoneInfoNotFoundError:  # pragma: no cover - defensive; validated on save
        zone = zoneinfo.ZoneInfo("UTC")
    local = moment.astimezone(zone)
    return local.strftime("%-I:%M %p %Z on %b %-d, %Y")
