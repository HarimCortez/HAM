"""Loads a church's `brand.json` (design-system/brands/<id>/) — deploy-time, read-only.

Q-026: another church deploys its own HAM by swapping `HAM_BRAND` and adding a folder here,
with no code change. See design-system/brands/README.md for the schema this reads and
design-system/tools/build_tokens.py for the CSS side of the same file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from django.conf import settings


class BrandConfigError(Exception):
    """The configured HAM_BRAND folder is missing or its brand.json is malformed."""


@dataclass(frozen=True)
class Brand:
    id: str
    name: str
    short_name: str
    mission_line: str
    display_font: str
    ui_font: str
    logo_on_dark: str
    logo_on_light: str
    logo_mark: str
    logo_alt: str


def brand_dir(brand_id: str) -> Path:
    return Path(settings.BASE_DIR) / "design-system" / "brands" / brand_id


@cache
def load_brand(brand_id: str | None = None) -> Brand:
    """Read and validate one brand's `brand.json`. Cached per process: this is deploy-time
    configuration, not something that changes while HAM is running."""
    brand_id = brand_id or settings.HAM_BRAND
    folder = brand_dir(brand_id)
    path = folder / "brand.json"
    if not path.exists():
        available = (
            sorted(p.name for p in folder.parent.iterdir() if (p / "brand.json").exists())
            if folder.parent.exists()
            else []
        )
        raise BrandConfigError(
            f"HAM_BRAND={brand_id!r} has no {path}. "
            f"Brands available: {', '.join(available) or 'none'}. "
            "See design-system/brands/README.md to add one."
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BrandConfigError(f"{path} is not valid JSON: {exc}") from exc

    try:
        church = data["church"]
        fonts = data["fonts"]
        logos = data["logos"]
        return Brand(
            id=brand_id,
            name=church["name"],
            short_name=church["shortName"],
            mission_line=church["missionLine"],
            display_font=fonts["display"],
            ui_font=fonts["ui"],
            logo_on_dark=logos["onDark"]["file"],
            logo_on_light=logos["onLight"]["file"],
            logo_mark=logos["mark"]["file"],
            logo_alt=logos["alt"],
        )
    except KeyError as exc:
        raise BrandConfigError(f"{path} is missing required field {exc}.") from exc
