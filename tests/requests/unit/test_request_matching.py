"""Keyed duplicate matching (PRD §9; Q-115). Table-driven normalization cases. Pure."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from ham.requests import matching
from ham.requests.matching import (
    MatchKeys,
    MatchReason,
    address_key,
    find_matches,
    match_keys,
    match_reasons,
    name_zip_key,
    normalize_email,
    normalize_name,
    normalize_phone,
    normalize_street,
    zip5,
)


# --- ZIP -------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("33101", "33101"),
        (" 33101 ", "33101"),
        ("33101-1234", "33101"),
        ("331011234", "33101"),
        ("33101 1234", "33101"),
        ("3310", None),
        ("331012", None),
        ("ABCDE", None),
        ("", None),
        (None, None),
        ("３３１０１", "33101"),  # full-width digits from some phone keyboards
    ],
)
def test_zip5(raw: str | None, expected: str | None) -> None:
    assert zip5(raw) == expected


# --- Email -----------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Doris@Example.com", "doris@example.com"),
        ("  doris@example.com  ", "doris@example.com"),
        ("doris@example.com.", "doris@example.com"),
        ("d.o.r.i.s+ham@gmail.com", "doris@gmail.com"),
        ("Doris.Smith@GoogleMail.com", "dorissmith@gmail.com"),
        ("doris+ham@example.com", "doris+ham@example.com"),  # non-Gmail: kept as typed
        ("doris.smith@example.com", "doris.smith@example.com"),
        ("not-an-email", None),
        ("a@b@c.com", None),
        ("doris @example.com", None),
        ("@example.com", None),
        ("doris@localhost", None),
        ("+tag@gmail.com", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_email(raw: str | None, expected: str | None) -> None:
    assert normalize_email(raw) == expected


# --- Phone -----------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("(305) 555-0142", "+13055550142"),
        ("305-555-0142", "+13055550142"),
        ("305.555.0142", "+13055550142"),
        ("+1 305 555 0142", "+13055550142"),
        ("1-305-555-0142", "+13055550142"),
        ("3055550142 ext 5", "+13055550142"),  # extension ignored
        ("305 555 0142 x12", "+13055550142"),
        ("555-0142", None),  # no area code: can't be a reliable key
        ("(305) 123-4567", None),  # impossible exchange
        ("12", None),
        ("call me", None),
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_normalize_phone(raw: str | None, expected: str | None) -> None:
    assert normalize_phone(raw) == expected


def test_foreign_number_with_country_code() -> None:
    assert normalize_phone("+52 55 1234 5678") == "+525512345678"


# --- Street ----------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("line1", "line2", "expected"),
    [
        # intake.md §11.5 example
        ("1400 N.W. Example Avenue Apt 2", None, "1400 NW EXAMPLE AVE #2"),
        ("1400 NW EXAMPLE AVE #2", None, "1400 NW EXAMPLE AVE #2"),
        ("1400 Northwest Example Ave.", "Apartment 2", "1400 NW EXAMPLE AVE #2"),
        ("1400 N W Example Av", "Unit 2", "1400 NW EXAMPLE AVE #2"),
        ("1400 nw example avenue, #2", None, "1400 NW EXAMPLE AVE #2"),
        ("1400 NW Example Ave", "Apt # 2", "1400 NW EXAMPLE AVE #2"),
        ("1400 NW Example Ave", "APT2", "1400 NW EXAMPLE AVE #2"),
        ("1400 NW Example Ave", "Suite 2", "1400 NW EXAMPLE AVE #2"),
        ("1400 NW Example Ave", "# 2", "1400 NW EXAMPLE AVE #2"),
        # suffixes
        ("12 Oak Street", None, "12 OAK ST"),
        ("12 Oak Str.", None, "12 OAK ST"),
        ("12 Palm Boulevard", None, "12 PALM BLVD"),
        ("12 Palm Blvd.", None, "12 PALM BLVD"),
        ("9 Coral Way", None, "9 CORAL WAY"),
        ("9 Bay Drive", None, "9 BAY DR"),
        ("9 Bay Court", None, "9 BAY CT"),
        ("9 Bay Terrace", None, "9 BAY TER"),
        ("9 Bay Parkway", None, "9 BAY PKWY"),
        ("9 Bay Circle", None, "9 BAY CIR"),
        ("9 Bay Lane", None, "9 BAY LN"),
        ("9 Bay Road", None, "9 BAY RD"),
        ("9 Bay Place", None, "9 BAY PL"),
        ("9 Bay Highway", None, "9 BAY HWY"),
        # directionals
        ("100 South Main St", None, "100 S MAIN ST"),
        ("100 S. Main St.", None, "100 S MAIN ST"),
        ("100 SW 8th Street", None, "100 SW 8TH ST"),
        ("100 Southwest 8th St", None, "100 SW 8TH ST"),
        ("100 S.W. 8th St", None, "100 SW 8TH ST"),
        ("100 Main St East", None, "100 MAIN ST E"),
        # mobile homes: lot / space / trailer all name the dwelling
        ("500 Palm Park Rd", "Lot 17", "500 PALM PARK RD #17"),
        ("500 Palm Park Rd", "Space 17", "500 PALM PARK RD #17"),
        ("500 Palm Park Rd", "Trailer 17", "500 PALM PARK RD #17"),
        # building and floor qualify; kept
        ("20 Elm St", "Building B Apt 3", "20 ELM ST BLDG B #3"),
        ("20 Elm St", "Bldg. B, Apt. 3", "20 ELM ST BLDG B #3"),
        ("20 Elm St", "Floor 2", "20 ELM ST FL 2"),
        # unit words without a number
        ("20 Elm St", "Rear", "20 ELM ST REAR"),
        ("20 Elm St", "Basement", "20 ELM ST BSMT"),
        # house numbers keep '-' and '/'
        ("123-45 Queens Blvd", None, "123-45 QUEENS BLVD"),
        ("12 1/2 Oak St", None, "12 1/2 OAK ST"),
        # accents and case
        ("7 Calle José Martí", None, "7 CALLE JOSE MARTI"),
        # dangling designator
        ("20 Elm St", "Apt", "20 ELM ST"),
        ("", None, None),
        (None, None, None),
        ("  ", "  ", None),
    ],
)
def test_normalize_street(line1: str | None, line2: str | None, expected: str | None) -> None:
    assert normalize_street(line1, line2) == expected


@pytest.mark.parametrize(
    ("a", "b"),
    [
        (("1400 N.W. Example Avenue Apt 2", None), ("1400 NW EXAMPLE AVE #2", None)),
        (("1400 NW Example Ave", "Apt 2"), ("1400 NW Example Ave Apt 2", None)),
        (("100 South Main Street", None), ("100 S Main St", None)),
    ],
)
def test_same_address_written_differently(
    a: tuple[str, str | None], b: tuple[str, str | None]
) -> None:
    assert address_key(a[0], a[1], "33101") == address_key(b[0], b[1], "33101-0001")


@pytest.mark.parametrize(
    ("a", "b"),
    [
        (("1400 NW Example Ave", "Apt 2"), ("1400 NW Example Ave", "Apt 3")),  # other unit
        (("1400 NW Example Ave", "Apt 2"), ("1400 NW Example Ave", None)),  # unit vs none
        (("1400 NW Example Ave", None), ("1400 NE Example Ave", None)),
        (("1400 NW Example Ave", None), ("1401 NW Example Ave", None)),
        (("12 Oak St", None), ("12 Oak Ave", None)),
    ],
)
def test_different_addresses_do_not_match(
    a: tuple[str, str | None], b: tuple[str, str | None]
) -> None:
    assert address_key(a[0], a[1], "33101") != address_key(b[0], b[1], "33101")


def test_address_key_needs_street_and_zip() -> None:
    assert address_key("12 Oak St", None, "33101") == "12 OAK ST|33101"
    assert address_key("12 Oak St", None, "33102") != address_key("12 Oak St", None, "33101")
    assert address_key("12 Oak St", None, None) is None
    assert address_key("12 Oak St", None, "331") is None
    assert address_key(None, None, "33101") is None


# --- Name + ZIP ------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Doris Smith", "DORIS SMITH"),
        ("doris   smith", "DORIS SMITH"),
        ("Smith, Doris", "DORIS SMITH"),
        ("Doris A. Smith", "DORIS SMITH"),
        ("Mrs. Doris Smith", "DORIS SMITH"),
        ("Dóris Smith", "DORIS SMITH"),
        ("Robert Jones Jr.", "JONES ROBERT"),
        ("Robert Jones III", "JONES ROBERT"),
        ("Mary O'Neil", "MARY ONEIL"),
        ("Mary O’Neil", "MARY ONEIL"),
        ("Ana María García-López", "ANA GARCIA LOPEZ MARIA"),
        ("Doris", None),  # one word matches too many people
        ("Dr. Doris", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_name(raw: str | None, expected: str | None) -> None:
    assert normalize_name(raw) == expected


def test_name_zip_key() -> None:
    assert name_zip_key("Doris Smith", "33101-4444") == "DORIS SMITH|33101"
    assert name_zip_key("Doris Smith", "33101") != name_zip_key("Doris Smith", "33102")
    assert name_zip_key("Doris Smith", None) is None
    assert name_zip_key("Doris", "33101") is None


# --- Reasons ---------------------------------------------------------------------------------
BASE = dict(
    full_name="Doris Smith",
    email="doris@example.com",
    phone="(305) 555-0142",
    line1="1400 NW Example Ave",
    line2="Apt 2",
    postal_code="33101",
)


def _keys(**changes: str | None) -> MatchKeys:
    return match_keys(**{**BASE, **changes})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("prior_changes", "expected"),
    [
        ({}, ("address", "phone", "email", "name_zip")),
        (
            {"full_name": "Someone Else", "email": "x@example.com", "phone": "305-555-0199"},
            ("address",),
        ),
        (
            {"line1": "9 Bay Dr", "line2": None, "email": "x@example.com", "full_name": "A B"},
            ("phone",),
        ),
        (
            {"line1": "9 Bay Dr", "line2": None, "phone": "305-555-0199", "full_name": "A B"},
            ("email",),
        ),
        (
            {"line1": "9 Bay Dr", "line2": None, "phone": "305-555-0199", "email": "x@example.com"},
            ("name_zip",),
        ),
        (
            {
                "full_name": "Smith, Doris",
                "line1": "1400 N.W. Example Avenue",
                "line2": "#2",
                "email": "DORIS@example.com",
                "phone": "+1 305 555 0142",
                "postal_code": "33101-9999",
            },
            ("address", "phone", "email", "name_zip"),
        ),
        (
            {
                "full_name": "Other Person",
                "email": "other@example.com",
                "phone": "305-555-0199",
                "line2": "Apt 3",
            },
            (),
        ),
        # same name, different ZIP: not a name+ZIP match
        (
            {
                "postal_code": "33102",
                "email": "o@example.com",
                "phone": "305-555-0199",
            },
            (),
        ),
    ],
)
def test_match_reasons(prior_changes: dict[str, str | None], expected: tuple[str, ...]) -> None:
    reasons = match_reasons(_keys(), _keys(**prior_changes))
    assert tuple(r.value for r in reasons) == expected
    assert all(isinstance(r, MatchReason) for r in reasons)


def test_missing_keys_never_match_each_other() -> None:
    empty = match_keys(
        full_name=None, email=None, phone=None, line1=None, line2=None, postal_code=None
    )
    assert empty == MatchKeys(None, None, None, None)
    assert match_reasons(empty, empty) == ()
    no_email = _keys(email=None)
    assert MatchReason.EMAIL not in match_reasons(no_email, _keys(email=None))


def test_find_matches_keeps_order_and_every_match() -> None:
    new = _keys()
    priors = [
        ("r3", _keys(full_name="X Y", email="x@example.com", phone=None, line2="Apt 9")),
        ("r2", _keys(email="other@example.com")),
        ("r1", _keys(full_name="Z Q", email=None, phone=None, line1="1 A St", line2=None)),
    ]
    result = find_matches(new, priors)
    assert [pid for pid, _ in result] == ["r2"]
    assert result[0][1] == (
        MatchReason.ADDRESS,
        MatchReason.PHONE,
        MatchReason.NAME_ZIP,
    )
    assert find_matches(new, []) == []


def test_reason_codes_match_the_request_match_model() -> None:
    """intake.md §3 RequestMatch.reasons: address | phone | email | name_zip."""
    assert [r.value for r in matching.REASON_ORDER] == ["address", "phone", "email", "name_zip"]


def test_no_score_no_description_no_ai() -> None:
    """Q-115: reasons only. The module must not take a description or return a score."""
    src = Path(matching.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    params = {
        a.arg
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        for a in node.args.args + node.args.kwonlyargs
    }
    assert not params & {"description", "score", "threshold", "similarity"}
    imported: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imported |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            imported.add(n.module or "")
    assert not any(
        m.split(".")[0] in {"django", "difflib", "rapidfuzz", "anthropic", "openai"}
        or m.startswith("ham.integrations")
        for m in imported
    )


def test_key_version_is_declared() -> None:
    assert matching.MATCH_KEY_VERSION == 1
