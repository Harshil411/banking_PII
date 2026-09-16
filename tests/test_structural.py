"""Tier-2 structural validators."""

from __future__ import annotations

import pytest

from app.validate.structural import (
    ein,
    email,
    itin,
    loan_number,
    money,
    nanp_phone,
    nmls_id,
    us_account_num,
    us_state,
    zip_code,
)


def test_ein_rejects_every_unassigned_prefix(vectors):
    for prefix in vectors["ein_unassigned_prefixes"]["values"]:
        ok, reason = ein(f"{prefix}-1234567")
        assert not ok, f"prefix {prefix} is unassigned and should be rejected"
        assert prefix in reason


def test_ein_accepts_assigned_prefixes():
    for prefix in ["01", "13", "45", "88", "95", "99"]:
        assert ein(f"{prefix}-1234567")[0], f"prefix {prefix} is assigned"


def test_nanp_rejects_published_invalid_forms(vectors):
    for value, why in vectors["nanp_invalid"]["values"]:
        ok, _ = nanp_phone(value)
        assert not ok, f"{value} should be rejected ({why})"


def test_nanp_accepts_the_reserved_fictional_range():
    """555-0100 through 555-0199 are reserved for fictional use and are structurally valid.

    The synthetic corpus uses them precisely because they are safe, so the
    validator must not treat them as malformed.
    """
    for value in ["(415) 555-0100", "(212) 555-0142", "(415) 555-0199"]:
        assert nanp_phone(value)[0], f"{value} is structurally valid"


@pytest.mark.parametrize("value", ["+1 (415) 555-0142", "1-415-555-0142", "4155550142"])
def test_nanp_tolerates_formatting(value):
    assert nanp_phone(value)[0]


def test_itin_group_range_boundaries():
    for group, expected in [
        (49, False), (50, True), (65, True), (66, False),
        (69, False), (70, True), (88, True), (89, False),
        (90, True), (92, True), (93, False), (94, True), (99, True),
    ]:
        ok, _ = itin(f"912-{group:02d}-1234")
        verdict = "valid" if expected else "invalid"
        assert ok is expected, f"ITIN group {group:02d} should be {verdict}"


def test_itin_requires_leading_nine():
    assert not itin("812-70-1234")[0]


def test_zip_range_boundaries():
    for value, expected in [("00500", False), ("00501", True), ("99950", True), ("99951", False)]:
        assert zip_code(value)[0] is expected, f"ZIP {value}"


def test_zip_plus_four():
    assert zip_code("94105-1804")[0]
    assert not zip_code("94105-0000")[0]
    assert not zip_code("94105-18")[0]


def test_email_structural_rules():
    assert email("j.doe@example.com")[0]
    assert email("borrower+tag@sub.example.co.uk")[0]
    for bad in [
        "j..doe@example.com",
        ".jdoe@example.com",
        "jdoe.@example.com",
        "jdoe@example",
        "jdoe@@example.com",
        "jdoe@-example.com",
        "jdoe@example.c",
        "jdoe@example.123",
    ]:
        assert not email(bad)[0], f"{bad} should be rejected"


def test_email_length_limits():
    assert not email("a" * 65 + "@example.com")[0]
    assert not email("a" * 250 + "@example.com")[0]


def test_account_number_rejects_degenerate_runs():
    assert us_account_num("483920117")[0]
    assert not us_account_num("00000000")[0]
    assert not us_account_num("12345678")[0]
    assert not us_account_num("98765432")[0]
    assert not us_account_num("1234567")[0]      # too short
    assert not us_account_num("1" * 18)[0]       # too long, and MERS_MIN territory


def test_account_number_rejects_wrapping_sequential_runs():
    """A run that wraps 9 -> 0 is still a sequential run.

    Plain subtraction reads that step as -9 and lets the value through. It is
    ordinary spreadsheet filler and belongs with the other degenerate cases.
    """
    assert not us_account_num("34567890")[0]
    assert not us_account_num("567890123")[0]
    assert not us_account_num("321098765")[0]


def test_account_number_excludes_mers_length():
    """18 digits is MERS_MIN territory; the two types must not both claim it."""
    seventeen = "48392011748392011"
    assert us_account_num(seventeen)[0], "17 digits is the top of the account range"
    assert not us_account_num(seventeen + "4")[0], "18 digits belongs to MERS_MIN"


def test_loan_number_prefix_and_length():
    assert loan_number("0012345678")[0]
    assert loan_number("LN4839201")[0]
    assert not loan_number("ABCD12345678")[0]
    assert not loan_number("0000000000")[0]
    assert not loan_number("123456")[0]


def test_nmls_id_rules():
    assert nmls_id("167890")[0]
    assert nmls_id("1234567")[0]
    assert not nmls_id("0000")[0]
    assert not nmls_id("0123456")[0]     # NMLS IDs are not zero padded
    assert not nmls_id("123")[0]
    assert not nmls_id("12345678")[0]


def test_us_state_membership():
    for value in ["CA", "NY", "DC", "PR", "California", "new hampshire", "District of Columbia"]:
        assert us_state(value)[0], f"{value} should be recognised"
    for value in ["XX", "ZZ", "Ontario", "Westeros", "Puerto"]:
        assert not us_state(value)[0], f"{value} should be rejected"


def test_us_state_reason_names_the_state():
    ok, reason = us_state("CA")
    assert ok and "California" in reason


def test_money_grouping_and_precision():
    for value in ["$1,204.55", "$250,000.00", "$42", "$0.99", "$1234.56", "$ 1,000"]:
        assert money(value)[0], f"{value} should be accepted"
    for value in ["$1,23.45", "$1,2345.00", "$10.123", "$"]:
        assert not money(value)[0], f"{value} should be rejected"


@pytest.mark.parametrize(
    "validator",
    [ein, itin, nanp_phone, email, zip_code, us_account_num, loan_number, nmls_id, us_state, money],
)
def test_every_validator_returns_a_reason(validator):
    """Reasons surface in the API's dropped[] array and in the demo UI."""
    for value in ["", "0", "xxxxxxxx"]:
        ok, reason = validator(value)
        assert isinstance(ok, bool)
        assert isinstance(reason, str) and reason, f"{validator.__name__}({value!r}) gave no reason"
