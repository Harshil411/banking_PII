"""Name-to-callable registry for validators.

An explicit dictionary, deliberately. Resolving ``"ssn"`` to a callable by
importing a dotted path from a config file would let a typo in the taxonomy
become an import error at request time, or worse, silently resolve to
something unintended. Here an unknown name fails at startup with a message
naming the valid options.
"""

from __future__ import annotations

from collections.abc import Callable

from app.validate import checksums, structural

#: A validator takes the matched text and returns ``(ok, human_readable_reason)``.
Validator = Callable[[str], tuple[bool, str]]

VALIDATORS: dict[str, Validator] = {
    # tier 1 -- arithmetic
    "ssn": checksums.ssn,
    "aba_routing": checksums.aba_routing,
    "credit_card": checksums.credit_card,
    "mers_min": checksums.mers_min,
    # tier 2 -- structural
    "ein": structural.ein,
    "itin": structural.itin,
    "nanp_phone": structural.nanp_phone,
    "email": structural.email,
    "zip_code": structural.zip_code,
    "us_account_num": structural.us_account_num,
    "loan_number": structural.loan_number,
    "nmls_id": structural.nmls_id,
    "us_state": structural.us_state,
    "money": structural.money,
}


def get(name: str) -> Validator:
    try:
        return VALIDATORS[name]
    except KeyError:
        raise KeyError(
            f"unknown validator {name!r}; registered validators are "
            f"{', '.join(sorted(VALIDATORS))}"
        ) from None
