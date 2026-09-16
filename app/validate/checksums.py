"""Tier-1 validators: rules that can prove a candidate impossible.

Every function here is pure, takes the raw matched text, and returns
``(ok, reason)``. The reason is user-facing -- it is surfaced in the API's
``dropped[]`` array and in the demo UI, so it explains the arithmetic rather
than naming the function that failed.

These deliberately import nothing from the taxonomy or the detectors. They
are the part of the system that has to be defensible on its own, and they
are tested against externally sourced vectors (published Federal Reserve
routing numbers, the standard Luhn test card numbers, the SSA's published
never-issued ranges) rather than against values this project generates. If
the only thing proving a validator correct were our own generator, a shared
misreading of the spec would be invisible in both.
"""

from __future__ import annotations

# Federal Reserve routing symbol ranges. The leading two digits of an ABA
# routing number identify the issuing district; everything outside these
# ranges has never been allocated.
_ABA_LEADING_RANGES: tuple[tuple[int, int], ...] = (
    (0, 12),    # Federal Reserve Banks
    (21, 32),   # thrift institutions
    (61, 72),   # electronic transaction identifiers
    (80, 80),   # traveller's cheques
)

_SSN_INVALID_AREAS = frozenset({"000", "666"})


def _digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def luhn(value: str) -> bool:
    """Mod-10 check over the digits of ``value``, including its check digit.

    Doubling every second digit from the right and subtracting 9 from any
    result above 9 is equivalent to, and cheaper than, summing the digits of
    the doubled value.
    """
    digits = _digits(value)
    if not digits:
        return False
    total = 0
    for index, char in enumerate(reversed(digits)):
        digit = ord(char) - 48
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def luhn_check_digit(base: str) -> str:
    """Return the digit that completes ``base`` into a valid mod-10 number.

    Used by the synthetic generator to construct identifiers forward. The
    generator must not call :func:`luhn` to search for a check digit, because
    then generator and validator would agree by construction and a shared
    misreading of the spec would never surface.
    """
    digits = _digits(base)
    total = 0
    # The appended check digit will occupy position 0 from the right, so the
    # rightmost digit of `base` sits at position 1 and is doubled.
    for index, char in enumerate(reversed(digits)):
        digit = ord(char) - 48
        if index % 2 == 0:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return str((10 - total % 10) % 10)


def ssn(value: str) -> tuple[bool, str]:
    """US Social Security Number, per the SSA's published assignment rules.

    Randomisation in 2011 removed the geographic meaning of the area number
    but did not retire these exclusions.
    """
    digits = _digits(value)
    if len(digits) != 9:
        return False, f"SSN must contain exactly 9 digits, found {len(digits)}"

    area, group, serial = digits[:3], digits[3:5], digits[5:]

    if area in _SSN_INVALID_AREAS:
        return False, f"area number {area} has never been issued"
    if area[0] == "9":
        return False, f"area number {area} is reserved for ITIN allocation, not SSNs"
    if group == "00":
        return False, "group number 00 has never been issued"
    if serial == "0000":
        return False, "serial number 0000 has never been issued"
    return True, "area, group and serial are all within issued ranges"


def aba_routing(value: str) -> tuple[bool, str]:
    """ABA routing transit number: district range plus a weighted mod-10 sum."""
    digits = _digits(value)
    if len(digits) != 9:
        return False, f"routing number must contain exactly 9 digits, found {len(digits)}"

    leading = int(digits[:2])
    if not any(low <= leading <= high for low, high in _ABA_LEADING_RANGES):
        return False, f"leading pair {digits[:2]} is not an assigned Federal Reserve range"

    d = [ord(c) - 48 for c in digits]
    checksum = (
        3 * (d[0] + d[3] + d[6]) + 7 * (d[1] + d[4] + d[7]) + (d[2] + d[5] + d[8])
    )
    if checksum % 10 != 0:
        return False, f"ABA checksum fails: weighted sum {checksum} is not a multiple of 10"
    return True, f"ABA checksum holds (weighted sum {checksum}) and district range is assigned"


def credit_card(value: str) -> tuple[bool, str]:
    """Payment card number: plausible length, then Luhn."""
    digits = _digits(value)
    if not 13 <= len(digits) <= 19:
        return False, f"card number must be 13-19 digits, found {len(digits)}"
    if not luhn(digits):
        return False, "Luhn check digit does not match"
    return True, "Luhn check digit matches"


def mers_min(value: str) -> tuple[bool, str]:
    """MERS Mortgage Identification Number.

    Eighteen digits: a 7-digit MERS Org ID, a 10-digit loan sequence, and a
    mod-10 check digit computed over the preceding seventeen.

    Unlike Luhn and ABA there is no convenient public corpus of known-good
    MINs to test against, so this validator carries more spec risk than its
    siblings. It is stated here rather than buried: if this reading of the
    MERS System Procedures Manual is wrong, tier-1 precision will look
    perfect on synthetic data and collapse on anything real.
    """
    digits = _digits(value)
    if len(digits) != 18:
        return False, f"MERS MIN must contain exactly 18 digits, found {len(digits)}"
    if int(digits[:7]) == 0:
        return False, "MERS Org ID 0000000 is not allocated"
    if not luhn(digits):
        return False, "mod-10 check digit does not match the 17-digit base"
    return True, "mod-10 check digit matches the 17-digit base"
