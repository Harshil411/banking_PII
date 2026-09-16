"""Tier-2 validators: deterministic rules that reject values the pattern admits.

Every validator here must be able to reject at least one string that matches
its own scanner regex. If it cannot, it adds nothing over the pattern and the
entity should be demoted to tier 3 rather than carrying a validator that only
ever agrees. ``tests/test_structural.py`` asserts exactly that property for
each one.

Like the tier-1 checksums, these are pure ``(value) -> (ok, reason)`` and the
reason is user-facing.
"""

from __future__ import annotations

import re

# IRS campus prefixes that have never been assigned to an EIN.
_EIN_UNASSIGNED_PREFIXES = frozenset(
    {"00", "07", "08", "09", "17", "18", "19", "28", "29", "49", "69", "70", "78", "79", "89",
     "96", "97"}
)

# Published ITIN group ranges. 89 and 93 sit in the gaps and are not issued.
_ITIN_GROUP_RANGES: tuple[tuple[int, int], ...] = ((50, 65), (70, 88), (90, 92), (94, 99))

# Lowest and highest assigned US ZIP codes.
_ZIP_MIN, _ZIP_MAX = 501, 99950

_US_STATES: dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin",
    "WY": "Wyoming", "DC": "District of Columbia", "PR": "Puerto Rico",
}
_STATE_ABBREVIATIONS = frozenset(_US_STATES)
_STATE_NAMES = frozenset(name.lower() for name in _US_STATES.values())

_MONEY_GROUPED = re.compile(r"\A\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?\Z")
_MONEY_PLAIN = re.compile(r"\A\d+(?:\.\d{1,2})?\Z")


def _digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def _is_repdigit(digits: str) -> bool:
    return len(set(digits)) == 1


def _is_sequential(digits: str) -> bool:
    """True for a strictly ascending or descending run, counting modulo 10.

    The modular step matters: "34567890" wraps from 9 to 0, so a plain
    subtraction sees a delta of -9 and concludes the run is not sequential.
    It is exactly the kind of filler that appears in spreadsheet columns and
    padded reference fields, and it should be rejected alongside "12345678".
    """
    deltas = {(ord(b) - ord(a)) % 10 for a, b in zip(digits, digits[1:], strict=False)}
    return deltas in ({1}, {9})


def ein(value: str) -> tuple[bool, str]:
    """Employer Identification Number: the prefix must be an assigned campus code."""
    digits = _digits(value)
    if len(digits) != 9:
        return False, f"EIN must contain exactly 9 digits, found {len(digits)}"
    prefix = digits[:2]
    if prefix in _EIN_UNASSIGNED_PREFIXES:
        return False, f"prefix {prefix} is not an IRS-assigned campus code"
    return True, f"prefix {prefix} is an assigned IRS campus code"


def itin(value: str) -> tuple[bool, str]:
    """Individual Taxpayer Identification Number: leading 9 and a published group range."""
    digits = _digits(value)
    if len(digits) != 9:
        return False, f"ITIN must contain exactly 9 digits, found {len(digits)}"
    if digits[0] != "9":
        return False, f"ITIN must begin with 9, found {digits[0]}"
    group = int(digits[3:5])
    if not any(low <= group <= high for low, high in _ITIN_GROUP_RANGES):
        return False, f"group {digits[3:5]} is outside the published ITIN ranges"
    return True, f"group {digits[3:5]} is within a published ITIN range"


def nanp_phone(value: str) -> tuple[bool, str]:
    """North American Numbering Plan subscriber number.

    Area code and exchange must each begin 2-9, and neither may be an N11
    service code (411, 611, 911 and siblings).
    """
    digits = _digits(value)
    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]
    if len(digits) != 10:
        return False, f"NANP number must contain 10 digits, found {len(digits)}"

    area, exchange = digits[:3], digits[3:6]
    if area[0] in "01":
        return False, f"area code {area} cannot begin with {area[0]}"
    if area[1] == "1" and area[2] == "1":
        return False, f"area code {area} is an N11 service code"
    if exchange[0] in "01":
        return False, f"exchange {exchange} cannot begin with {exchange[0]}"
    if exchange[1] == "1" and exchange[2] == "1":
        return False, f"exchange {exchange} is an N11 service code"
    if _is_repdigit(digits):
        return False, f"{digits} is a single repeated digit, not a subscriber number"
    return True, f"area code {area} and exchange {exchange} are both valid NANP codes"


def email(value: str) -> tuple[bool, str]:
    """Email address: the structural rules the scanner pattern is too loose to express."""
    if value.count("@") != 1:
        return False, "address must contain exactly one @"
    local, _, domain = value.partition("@")

    if len(value) > 254:
        return False, f"address exceeds 254 characters ({len(value)})"
    if not 1 <= len(local) <= 64:
        return False, f"local part must be 1-64 characters, found {len(local)}"
    if local.startswith(".") or local.endswith("."):
        return False, "local part cannot start or end with a dot"
    if ".." in local:
        return False, "local part cannot contain consecutive dots"

    labels = domain.split(".")
    if len(labels) < 2:
        return False, "domain must contain at least one dot"
    if any(not label for label in labels):
        return False, "domain cannot contain an empty label"
    if any(label.startswith("-") or label.endswith("-") for label in labels):
        return False, "domain labels cannot start or end with a hyphen"
    if any(len(label) > 63 for label in labels):
        return False, "domain labels cannot exceed 63 characters"
    if not labels[-1].isalpha() or len(labels[-1]) < 2:
        return False, f"top-level domain {labels[-1]!r} must be at least two letters"
    return True, "local part and domain are both well formed"


def zip_code(value: str) -> tuple[bool, str]:
    """US postal code: within the assigned 00501-99950 range."""
    base, _, plus4 = value.partition("-")
    if not base.isdigit() or len(base) != 5:
        return False, "ZIP must begin with exactly 5 digits"
    numeric = int(base)
    if not _ZIP_MIN <= numeric <= _ZIP_MAX:
        return False, f"{base} is outside the assigned range {_ZIP_MIN:05d}-{_ZIP_MAX}"
    if plus4:
        if not plus4.isdigit() or len(plus4) != 4:
            return False, "ZIP+4 segment must be exactly 4 digits"
        if plus4 == "0000":
            return False, "ZIP+4 segment 0000 is not assigned"
    return True, f"{base} is within the assigned ZIP range"


def us_account_num(value: str) -> tuple[bool, str]:
    """Deposit or escrow account number: length plus degenerate-pattern rejection.

    This is the weakest tier-2 validator in the set, and honestly so: there is
    no checksum on a US deposit account number. It still earns its tier by
    rejecting the repdigit and sequential runs that regex-only detection
    reliably produces from tables, reference numbers and padding.
    """
    digits = _digits(value)
    if not 8 <= len(digits) <= 17:
        return False, f"account number must be 8-17 digits, found {len(digits)}"
    if _is_repdigit(digits):
        return False, f"{digits} is a single repeated digit, not an account number"
    if _is_sequential(digits):
        return False, f"{digits} is a sequential run, not an account number"
    return True, f"{len(digits)}-digit account number with no degenerate pattern"


def loan_number(value: str) -> tuple[bool, str]:
    """Servicer loan number: no industry format, so shape plus degenerate rejection."""
    prefix = "".join(ch for ch in value if ch.isalpha())
    digits = _digits(value)
    if len(prefix) > 3:
        return False, f"loan number prefix {prefix!r} exceeds three letters"
    if not 7 <= len(digits) <= 12:
        return False, f"loan number must contain 7-12 digits, found {len(digits)}"
    if _is_repdigit(digits):
        return False, f"{digits} is a single repeated digit, not a loan number"
    return True, f"{len(digits)}-digit loan number with a valid prefix"


def nmls_id(value: str) -> tuple[bool, str]:
    """NMLS identifier: 4-7 digits, no leading zero, not a repdigit."""
    digits = _digits(value)
    if not 4 <= len(digits) <= 7:
        return False, f"NMLS ID must be 4-7 digits, found {len(digits)}"
    if digits[0] == "0":
        return False, "NMLS IDs are not zero-padded"
    if _is_repdigit(digits):
        return False, f"{digits} is a single repeated digit, not an NMLS ID"
    return True, f"{len(digits)}-digit NMLS identifier"


def us_state(value: str) -> tuple[bool, str]:
    """US state, DC or territory: closed-set membership."""
    stripped = value.strip().rstrip(",")
    if stripped in _STATE_ABBREVIATIONS:
        return True, f"{stripped} is the postal abbreviation for {_US_STATES[stripped]}"
    if stripped.lower() in _STATE_NAMES:
        return True, f"{stripped} is a US state, district or territory"
    return False, f"{stripped!r} is not a US state, district or territory"


def money(value: str) -> tuple[bool, str]:
    """Currency amount: correct thousands grouping and at most two decimal places."""
    body = value.lstrip("$").strip()
    if not body:
        return False, "amount is empty"
    if "," in body:
        if not _MONEY_GROUPED.match(body):
            return False, f"{body!r} has malformed thousands grouping"
    elif not _MONEY_PLAIN.match(body):
        return False, f"{body!r} is not a well-formed amount"
    if "." in body and len(body.rsplit(".", 1)[1]) > 2:
        return False, f"{body!r} has sub-cent precision"
    return True, "well-formed currency amount"
