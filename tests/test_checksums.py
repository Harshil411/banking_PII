"""Tier-1 validators against externally sourced vectors."""

from __future__ import annotations

import pytest

from app.validate.checksums import (
    aba_routing,
    credit_card,
    luhn,
    luhn_check_digit,
    mers_min,
    ssn,
)


def test_aba_accepts_published_routing_numbers(vectors):
    for value, label in vectors["aba_routing_valid"]["values"]:
        ok, reason = aba_routing(value)
        assert ok, f"{value} ({label}) should validate, got: {reason}"


def test_aba_rejects_perturbed_and_unassigned(vectors):
    for value, why in vectors["aba_routing_invalid"]["values"]:
        ok, _ = aba_routing(value)
        assert not ok, f"{value} should be rejected ({why})"


def test_luhn_accepts_published_test_cards(vectors):
    for value, label in vectors["luhn_valid"]["values"]:
        ok, reason = credit_card(value)
        assert ok, f"{value} ({label}) should validate, got: {reason}"


def test_luhn_rejects_perturbed_test_cards(vectors):
    for value, why in vectors["luhn_invalid"]["values"]:
        ok, _ = credit_card(value)
        assert not ok, f"{value} should be rejected ({why})"


def test_ssn_rejects_never_issued_ranges(vectors):
    for value, why in vectors["ssn_invalid"]["values"]:
        ok, reason = ssn(value)
        assert not ok, f"{value} should be rejected ({why})"
        assert reason, "a rejection must carry a human-readable reason"


def test_ssn_accepts_structurally_conformant(vectors):
    for value, label in vectors["ssn_structurally_valid"]["values"]:
        ok, reason = ssn(value)
        assert ok, f"{value} ({label}) should validate, got: {reason}"


@pytest.mark.parametrize("separator", ["", "-", " "])
def test_ssn_is_separator_insensitive(separator):
    value = separator.join(["457", "55", "1275"])
    assert ssn(value)[0]


def test_luhn_check_digit_completes_a_valid_number():
    """The generator's forward construction must agree with the validator.

    This is the only place the two are allowed to meet. synth/providers.py
    calls luhn_check_digit to build values and never calls luhn to search for
    one, so that a wrong reading of the spec would surface as a test failure
    here rather than as silent mutual agreement.
    """
    for base in ["10000230000000001", "40001110000098765", "7654321123456789", "1" * 17]:
        completed = base + luhn_check_digit(base)
        assert luhn(completed), f"{completed} should satisfy mod-10"


def test_mers_min_requires_eighteen_digits():
    ok, reason = mers_min("10000230000000001")
    assert not ok and "18 digits" in reason


def test_mers_min_rejects_unallocated_org_id():
    ok, reason = mers_min("0" * 18)
    assert not ok and "Org ID" in reason


def test_mers_min_accepts_forward_constructed_values():
    for org, sequence in [("1000023", "0000000001"), ("1000302", "0004839201")]:
        base = org + sequence
        ok, reason = mers_min(base + luhn_check_digit(base))
        assert ok, reason


def test_mers_min_rejects_single_digit_perturbation():
    base = "1000023" + "0000000001"
    correct = int(luhn_check_digit(base))
    assert not mers_min(base + str((correct + 1) % 10))[0]


def test_luhn_rejects_empty_input():
    assert not luhn("")
    assert not luhn("no digits here")
