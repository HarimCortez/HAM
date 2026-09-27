"""`church_profile()` — the one read-only object templates and other modules use for church
identity (foundation.md §2.2). Merges the deploy-time brand layer with the Admin-editable
`ChurchProfile` row. Templates use `{church.*}` only; never a literal church name/phone/email
anywhere else (CLAUDE.md, design-system/brands/README.md).
"""

from __future__ import annotations

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
    time_zone: str
    website_url: str


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
        time_zone=row.time_zone,
        website_url=row.website_url,
    )
