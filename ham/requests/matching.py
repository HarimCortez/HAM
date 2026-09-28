"""Keyed duplicate matching for requests (PRD §9; Q-115). Rules-owned, pure.

Q-115 (proposed default in use): a new request is flagged against earlier ones on the same
address (including the unit), the same phone, the same email, or the same name within the
same ZIP code. Leaders see the reasons as chips. There is NO score, NO description or text
similarity and NO AI in V1, and a flag never changes a request's outcome (§9).

Every key is a normalized string, or ``None`` when the input cannot make a reliable key
(an empty field never matches another empty field). Services may store the keys hashed
(HMAC) -- equality is all that matters. ``MATCH_KEY_VERSION`` changes whenever
normalization changes, so stored keys can be recomputed rather than silently drifting.

The keys contain personal data; never log them or put them in outbox payloads (§68).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeVar

import phonenumbers

# PRD-GAP Q-115: proposed default in use; owner may change.
MATCH_KEY_VERSION = 1

DEFAULT_PHONE_REGION = "US"


class MatchReason(StrEnum):
    ADDRESS = "address"
    PHONE = "phone"
    EMAIL = "email"
    NAME_ZIP = "name_zip"


# Order in which reasons are reported (strongest identity signal first).
REASON_ORDER: tuple[MatchReason, ...] = (
    MatchReason.ADDRESS,
    MatchReason.PHONE,
    MatchReason.EMAIL,
    MatchReason.NAME_ZIP,
)


# --------------------------------------------------------------------------------------
# Text helpers
# --------------------------------------------------------------------------------------
def _fold(text: str) -> str:
    """NFKD, accents removed, upper-cased: 'José' -> 'JOSE', full-width digits -> ASCII."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.upper()


def zip5(postal_code: str | None) -> str | None:
    """First five digits of a US ZIP / ZIP+4 ('33101-1234' -> '33101'); else None."""
    if not postal_code:
        return None
    m = re.fullmatch(r"\s*(\d{5})(?:\s*-?\s*\d{4})?\s*", _fold(postal_code))
    return m.group(1) if m else None


# --------------------------------------------------------------------------------------
# Email
# --------------------------------------------------------------------------------------
_GMAIL_DOMAINS = frozenset({"gmail.com", "googlemail.com"})


def normalize_email(raw: str | None) -> str | None:
    """Lower-cased, trimmed address; Gmail dots and '+tags' removed (they reach the same
    mailbox). Other providers keep their local part as typed (lower-cased), since not all
    of them treat '+' or '.' specially. Returns None for anything that isn't an address."""
    if not raw:
        return None
    text = unicodedata.normalize("NFKC", raw).strip().lower()
    if text.count("@") != 1 or any(ch.isspace() for ch in text):
        return None
    local, domain = text.split("@")
    domain = domain.rstrip(".")
    if not local or "." not in domain or domain.startswith("."):
        return None
    if domain in _GMAIL_DOMAINS:
        local = local.split("+", 1)[0].replace(".", "")
        domain = "gmail.com"
        if not local:
            return None
    return f"{local}@{domain}"


# --------------------------------------------------------------------------------------
# Phone
# --------------------------------------------------------------------------------------
def normalize_phone(raw: str | None, region: str = DEFAULT_PHONE_REGION) -> str | None:
    """E.164 ('+13055550142') for a valid number; extensions are ignored. A number that
    can't be valid (too short, no area code, impossible exchange) gives None rather than a
    key that could match unrelated people."""
    if not raw or not raw.strip():
        return None
    try:
        parsed = phonenumbers.parse(raw, region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    parsed.extension = None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


# --------------------------------------------------------------------------------------
# Address (USPS Publication 28 abbreviations)
# --------------------------------------------------------------------------------------
# Street suffixes (Pub 28 appendix C1): the common residential ones, every usual spelling.
STREET_SUFFIXES: dict[str, str] = {
    "ALLEY": "ALY", "ALLEE": "ALY", "ALLY": "ALY", "ALY": "ALY",
    "AVENUE": "AVE", "AV": "AVE", "AVEN": "AVE", "AVENU": "AVE", "AVN": "AVE", "AVNUE": "AVE",
    "AVE": "AVE",
    "BOULEVARD": "BLVD", "BOUL": "BLVD", "BOULV": "BLVD", "BLVD": "BLVD",
    "CIRCLE": "CIR", "CIRC": "CIR", "CIRCL": "CIR", "CRCL": "CIR", "CRCLE": "CIR", "CIR": "CIR",
    "COURT": "CT", "CRT": "CT", "CT": "CT",
    "COVE": "CV", "CV": "CV",
    "CROSSING": "XING", "CRSSNG": "XING", "XING": "XING",
    "DRIVE": "DR", "DRIV": "DR", "DRV": "DR", "DR": "DR",
    "EXPRESSWAY": "EXPY", "EXPY": "EXPY",
    "FREEWAY": "FWY", "FWY": "FWY",
    "HIGHWAY": "HWY", "HIGHWY": "HWY", "HIWAY": "HWY", "HIWY": "HWY", "HWAY": "HWY", "HWY": "HWY",
    "LANE": "LN", "LN": "LN",
    "LOOP": "LOOP", "LOOPS": "LOOP",
    "PARKWAY": "PKWY", "PARKWY": "PKWY", "PKWAY": "PKWY", "PKY": "PKWY", "PKWY": "PKWY",
    "PLACE": "PL", "PL": "PL",
    "PLAZA": "PLZ", "PLZA": "PLZ", "PLZ": "PLZ",
    "POINT": "PT", "PT": "PT",
    "ROAD": "RD", "RD": "RD",
    "ROW": "ROW",
    "RUN": "RUN",
    "SQUARE": "SQ", "SQR": "SQ", "SQRE": "SQ", "SQU": "SQ", "SQ": "SQ",
    "STREET": "ST", "STRT": "ST", "STR": "ST", "ST": "ST",
    "TERRACE": "TER", "TERR": "TER", "TER": "TER",
    "TRAIL": "TRL", "TRAILS": "TRL", "TRLS": "TRL", "TRL": "TRL",
    "TRACE": "TRCE", "TRCE": "TRCE",
    "TURNPIKE": "TPKE", "TRNPK": "TPKE", "TURNPK": "TPKE", "TPKE": "TPKE",
    "WAY": "WAY", "WY": "WAY",
}  # fmt: skip

DIRECTIONALS: dict[str, str] = {
    "NORTH": "N", "N": "N",
    "SOUTH": "S", "S": "S",
    "EAST": "E", "E": "E",
    "WEST": "W", "W": "W",
    "NORTHEAST": "NE", "NE": "NE",
    "NORTHWEST": "NW", "NW": "NW",
    "SOUTHEAST": "SE", "SE": "SE",
    "SOUTHWEST": "SW", "SW": "SW",
}  # fmt: skip

# Two single-letter directionals written apart ("N W", from "N.W.") are one directional.
_DIRECTIONAL_PAIRS = {("N", "E"): "NE", ("N", "W"): "NW", ("S", "E"): "SE", ("S", "W"): "SW"}

# Secondary unit designators (Pub 28 appendix C2) that name one dwelling. They all collapse
# to '#', so "Apt 2", "Unit 2", "Suite 2", "Lot 2" and "#2" are the same unit: people
# describe the same apartment or mobile-home lot in different words.
UNIT_DESIGNATORS: frozenset[str] = frozenset(
    {
        "#", "APARTMENT", "APT", "UNIT", "SUITE", "STE", "ROOM", "RM", "LOT", "SPACE", "SPC",
        "TRAILER", "TRLR", "NUMBER", "NO", "NUM", "PENTHOUSE", "PH",
    }
)  # fmt: skip
# Designators that qualify rather than name the dwelling; kept, abbreviated.
OTHER_DESIGNATORS: dict[str, str] = {
    "BUILDING": "BLDG", "BLDG": "BLDG", "FLOOR": "FL", "FL": "FL",
}  # fmt: skip
# Designators that take no number (Pub 28): the word itself is the unit.
UNIT_WORDS: dict[str, str] = {
    "BASEMENT": "BSMT", "BSMT": "BSMT", "FRONT": "FRNT", "FRNT": "FRNT", "REAR": "REAR",
    "UPPER": "UPPR", "UPPR": "UPPR", "LOWER": "LOWR", "LOWR": "LOWR",
}  # fmt: skip

_GLUED_UNIT = re.compile(r"^(APT|UNIT|STE|RM|LOT|SPC|TRLR|NO)(\d[A-Z0-9-]*)$")


def _address_tokens(text: str) -> list[str]:
    folded = _fold(text)
    folded = folded.replace("#", " # ")
    # Periods, commas and other punctuation become spaces; '-' and '/' stay (house
    # numbers such as "123-45" and "12 1/2" keep their meaning).
    folded = re.sub(r"[^A-Z0-9#/\- ]+", " ", folded)
    return [t.strip("-") for t in folded.split() if t.strip("-")]


def _normalize_street_tokens(tokens: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        nxt = tokens[i + 1] if i + 1 < len(tokens) else None
        glued = _GLUED_UNIT.match(tok)
        if glued:
            out.append("#" + glued.group(2))
            i += 1
            continue
        if tok in UNIT_DESIGNATORS:
            # "APT 2", "# 2", "APT # 2"
            j = i + 1
            while j < len(tokens) and tokens[j] in UNIT_DESIGNATORS:
                j += 1
            if j < len(tokens):
                out.append("#" + tokens[j])
                i = j + 1
            else:
                i = j  # a dangling designator with no unit id carries no information
            continue
        if tok in OTHER_DESIGNATORS and nxt is not None:
            out.extend([OTHER_DESIGNATORS[tok], nxt])
            i += 2
            continue
        if tok in UNIT_WORDS:  # symmetric: "Front St" becomes "FRNT ST" on both sides
            out.append(UNIT_WORDS[tok])
            i += 1
            continue
        if tok in DIRECTIONALS:
            d = DIRECTIONALS[tok]
            if nxt is not None and (d, nxt) in _DIRECTIONAL_PAIRS:
                out.append(_DIRECTIONAL_PAIRS[(d, nxt)])
                i += 2
                continue
            out.append(d)
            i += 1
            continue
        out.append(STREET_SUFFIXES.get(tok, tok))
        i += 1
    return out


def normalize_street(line1: str | None, line2: str | None = None) -> str | None:
    """Street address in USPS style: 'Apt 2' -> '#2', 'Avenue' -> 'AVE', 'N.W.' -> 'NW'.

    Both lines are read together, because people put the unit on either line. Pure text
    normalization: no geocoding and no address database (third parties, §68)."""
    text = " ".join(part for part in (line1, line2) if part and part.strip())
    tokens = _normalize_street_tokens(_address_tokens(text))
    return " ".join(tokens) or None


def address_key(line1: str | None, line2: str | None, postal_code: str | None) -> str | None:
    """'1400 NW EXAMPLE AVE #2|33101'. None without a street or a 5-digit ZIP, because a
    street alone repeats across towns."""
    street = normalize_street(line1, line2)
    z = zip5(postal_code)
    if street is None or z is None:
        return None
    return f"{street}|{z}"


# --------------------------------------------------------------------------------------
# Name + ZIP
# --------------------------------------------------------------------------------------
NAME_TITLES_AND_SUFFIXES: frozenset[str] = frozenset(
    {
        "MR", "MRS", "MS", "MISS", "DR", "REV", "SR", "JR", "II", "III", "IV",
        "SISTER", "BROTHER", "ELDER", "PASTOR",
    }
)  # fmt: skip


def normalize_name(full_name: str | None) -> str | None:
    """Accents, case, punctuation, titles, generational suffixes and single-letter initials
    are ignored and the words sorted, so 'Smith, Doris A.' == 'doris smith' == 'Dóris Smith'.
    Needs at least two words (a first name alone matches too many people)."""
    if not full_name:
        return None
    folded = _fold(full_name).replace("'", "").replace("’", "")
    words = re.sub(r"[^A-Z0-9]+", " ", folded).split()
    words = [w for w in words if len(w) > 1 and w not in NAME_TITLES_AND_SUFFIXES]
    if len(words) < 2:
        return None
    return " ".join(sorted(words))


def name_zip_key(full_name: str | None, postal_code: str | None) -> str | None:
    name = normalize_name(full_name)
    z = zip5(postal_code)
    if name is None or z is None:
        return None
    return f"{name}|{z}"


# --------------------------------------------------------------------------------------
# Keys and comparison
# --------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class MatchKeys:
    address: str | None
    phone: str | None
    email: str | None
    name_zip: str | None


def match_keys(
    *,
    full_name: str | None,
    email: str | None,
    phone: str | None,
    line1: str | None,
    line2: str | None,
    postal_code: str | None,
    phone_region: str = DEFAULT_PHONE_REGION,
) -> MatchKeys:
    """All four keys for one request."""
    return MatchKeys(
        address=address_key(line1, line2, postal_code),
        phone=normalize_phone(phone, phone_region),
        email=normalize_email(email),
        name_zip=name_zip_key(full_name, postal_code),
    )


def match_reasons(new: MatchKeys, prior: MatchKeys) -> tuple[MatchReason, ...]:
    """Why ``prior`` may be the same household or person as ``new``: reason codes in
    ``REASON_ORDER``, empty if none. A missing key never matches."""
    pairs = {
        MatchReason.ADDRESS: (new.address, prior.address),
        MatchReason.PHONE: (new.phone, prior.phone),
        MatchReason.EMAIL: (new.email, prior.email),
        MatchReason.NAME_ZIP: (new.name_zip, prior.name_zip),
    }
    return tuple(r for r in REASON_ORDER if pairs[r][0] is not None and pairs[r][0] == pairs[r][1])


_Id = TypeVar("_Id")


def find_matches(
    new: MatchKeys, priors: Iterable[tuple[_Id, MatchKeys]]
) -> list[tuple[_Id, tuple[MatchReason, ...]]]:
    """Every earlier request with at least one reason, in the order given (the caller passes
    retained history, newest first). Never scores and never drops a match."""
    out: list[tuple[_Id, tuple[MatchReason, ...]]] = []
    for prior_id, keys in priors:
        reasons = match_reasons(new, keys)
        if reasons:
            out.append((prior_id, reasons))
    return out
