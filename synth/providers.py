"""Value providers for the synthetic corpus.

Each provider knows how to produce two things for its entity type:

``valid``
    A well-formed value. Tier-1 identifiers here are checksum-CORRECT. That
    is deliberate and worth being explicit about: if the corpus contained only
    deliberately-broken identifiers, every tier-1 validator would reject every
    true positive, recall would collapse, and it would look like a detection
    bug for a day. A randomly generated well-formed SSN is no more a real
    person's record than a random nine-digit number -- there is no linkage to
    any identity in the synthetic document.

``adversarial``
    A near-miss: a value that passes the type's scanner pattern and fails its
    validator. These are the corpus's reason for existing. "Checksum
    validation rejected N% of regex-passing near-misses" is the claim this
    project is built to support, and it is not computable without them.

Safety conventions, so nothing here can collide with a live record:

* phone numbers use 555-0100..555-0199, reserved for fictional use
* email domains use example.com / example.org / example.net, reserved by
  RFC 2606 and guaranteed never to be registered
* payment card numbers are built from published processor test prefixes

CHECK DIGITS ARE CONSTRUCTED FORWARD. ``luhn_check_digit`` computes the digit
directly; nothing here calls ``luhn`` to search for one. If generator and
validator both derived their answer from the same routine they would agree
with each other by construction, and a misreading of a specification would be
invisible in both. Tests assert the two agree; they must be able to disagree.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from random import Random

from app.core.types import ValueKind
from app.validate.checksums import luhn_check_digit

# Published Federal Reserve routing symbol prefixes, kept in the assigned
# ranges so a generated routing number is structurally plausible.
_ABA_PREFIXES = ("01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12",
                 "21", "22", "26", "28", "31", "61", "62", "65", "72")
_CARD_PREFIXES = ("4111", "4012", "5555", "5105", "6011")
_EIN_PREFIXES = ("01", "13", "20", "26", "27", "33", "45", "46", "47", "81", "82", "85", "92", "95")
_ITIN_GROUPS = tuple(
    g for lo, hi in ((50, 65), (70, 88), (90, 92), (94, 99)) for g in range(lo, hi + 1)
)
_STATES = ("AL", "AK", "AZ", "CA", "CO", "CT", "FL", "GA", "IL", "MA", "MD", "MI", "MN",
           "NC", "NJ", "NY", "OH", "OR", "PA", "TX", "VA", "WA", "WI")
_STATE_NAMES = ("California", "Texas", "Florida", "New York", "Illinois", "Ohio",
                "Pennsylvania", "Georgia", "North Carolina", "Michigan", "New Jersey",
                "Washington", "Massachusetts", "New Hampshire", "District of Columbia")
_EMAIL_DOMAINS = ("example.com", "example.org", "example.net")


@dataclass(frozen=True, slots=True)
class GeneratedValue:
    text: str
    kind: ValueKind
    note: str = ""


@dataclass(frozen=True, slots=True)
class Provider:
    """A pair of generators for one entity type.

    ``adversarial`` is ``None`` for tier-3 types: with no validator there is
    nothing for a near-miss to defeat, so generating one would be theatre.
    """

    valid: Callable[[Random], str]
    adversarial: Callable[[Random], tuple[str, str]] | None = None

    def make(self, rng: Random, kind: ValueKind) -> GeneratedValue:
        if kind is ValueKind.VALID:
            return GeneratedValue(self.valid(rng), ValueKind.VALID)
        if kind is ValueKind.ADVERSARIAL:
            if self.adversarial is None:
                raise ValueError("this provider has no adversarial form")
            text, note = self.adversarial(rng)
            return GeneratedValue(text, ValueKind.ADVERSARIAL, note)
        raise ValueError(f"providers do not generate {kind}")

    @property
    def has_adversarial(self) -> bool:
        return self.adversarial is not None


def _sep(rng: Random, options: tuple[str, ...] = ("-", " ", "")) -> str:
    return rng.choice(options)


# --------------------------------------------------------------------------
# tier 1
# --------------------------------------------------------------------------


def _ssn_valid(rng: Random) -> str:
    area = rng.choice([n for n in range(1, 900) if n != 666])
    group = rng.randint(1, 99)
    serial = rng.randint(1, 9999)
    s = _sep(rng, ("-", "-", " ", ""))
    return f"{area:03d}{s}{group:02d}{s}{serial:04d}"


def _ssn_adversarial(rng: Random) -> tuple[str, str]:
    choice = rng.choice(["area_000", "area_666", "area_9xx", "group_00", "serial_0000"])
    group, serial = rng.randint(1, 99), rng.randint(1, 9999)
    if choice == "area_000":
        return f"000-{group:02d}-{serial:04d}", "area number 000 is never issued"
    if choice == "area_666":
        return f"666-{group:02d}-{serial:04d}", "area number 666 is never issued"
    if choice == "area_9xx":
        return f"{rng.randint(900, 999)}-{group:02d}-{serial:04d}", "900-999 is ITIN space"
    if choice == "group_00":
        return f"{rng.randint(1, 665):03d}-00-{serial:04d}", "group number 00 is never issued"
    return f"{rng.randint(1, 665):03d}-{group:02d}-0000", "serial number 0000 is never issued"


def _aba_valid(rng: Random) -> str:
    prefix = rng.choice(_ABA_PREFIXES)
    body = f"{rng.randint(0, 999999):06d}"
    digits = [int(c) for c in prefix + body]
    # Computed here rather than by calling aba_routing() in a loop: generator
    # and validator must be able to disagree, or a misread spec hides in both.
    weighted = (
        3 * (digits[0] + digits[3] + digits[6])
        + 7 * (digits[1] + digits[4] + digits[7])
        + digits[2]
        + digits[5]
    )
    check = (10 - weighted % 10) % 10
    return prefix + body + str(check)


def _aba_adversarial(rng: Random) -> tuple[str, str]:
    if rng.random() < 0.5:
        valid = _aba_valid(rng)
        index = rng.randrange(9)
        digit = str((int(valid[index]) + rng.randint(1, 9)) % 10)
        perturbed = valid[:index] + digit + valid[index + 1 :]
        return perturbed, "single-digit perturbation breaks the checksum"
    unassigned = rng.choice(("13", "45", "50", "90", "99"))
    return unassigned + f"{rng.randint(0, 9999999):07d}", "leading pair is not an assigned district"


def _card_valid(rng: Random) -> str:
    base = rng.choice(_CARD_PREFIXES) + f"{rng.randrange(10 ** 11):011d}"
    full = base + luhn_check_digit(base)
    s = _sep(rng, (" ", "-", ""))
    return s.join(full[i:i + 4] for i in range(0, 16, 4))


def _card_adversarial(rng: Random) -> tuple[str, str]:
    base = rng.choice(_CARD_PREFIXES) + f"{rng.randrange(10 ** 11):011d}"
    wrong = str((int(luhn_check_digit(base)) + rng.randint(1, 9)) % 10)
    full = base + wrong
    s = _sep(rng, (" ", "-", ""))
    return s.join(full[i:i + 4] for i in range(0, 16, 4)), "Luhn check digit does not match"


def _mers_base(rng: Random) -> str:
    return f"{rng.randint(1000000, 1999999)}{rng.randrange(10 ** 10):010d}"


def _mers_valid(rng: Random) -> str:
    base = _mers_base(rng)
    full = base + luhn_check_digit(base)
    if rng.random() < 0.3:
        return f"{full[:7]}-{full[7:17]}-{full[17]}"
    return full


def _mers_adversarial(rng: Random) -> tuple[str, str]:
    base = _mers_base(rng)
    wrong = str((int(luhn_check_digit(base)) + rng.randint(1, 9)) % 10)
    return base + wrong, "mod-10 check digit does not match the 17-digit base"


# --------------------------------------------------------------------------
# tier 2
# --------------------------------------------------------------------------


def _ein_valid(rng: Random) -> str:
    return f"{rng.choice(_EIN_PREFIXES)}-{rng.randrange(10 ** 7):07d}"


def _ein_adversarial(rng: Random) -> tuple[str, str]:
    prefix = rng.choice(("00", "07", "17", "28", "49", "69", "89", "96"))
    return f"{prefix}-{rng.randrange(10 ** 7):07d}", f"prefix {prefix} is not IRS-assigned"


def _itin_valid(rng: Random) -> str:
    return f"9{rng.randint(0, 99):02d}-{rng.choice(_ITIN_GROUPS):02d}-{rng.randrange(10 ** 4):04d}"


def _itin_adversarial(rng: Random) -> tuple[str, str]:
    group = rng.choice((49, 66, 67, 68, 69, 89, 93))
    return f"9{rng.randint(0, 99):02d}-{group:02d}-{rng.randrange(10 ** 4):04d}", (
        f"group {group:02d} is outside the published ITIN ranges"
    )


def _phone_valid(rng: Random) -> str:
    # 555-0100..555-0199 is reserved for fictional use.
    area = rng.choice((202, 212, 312, 404, 415, 512, 617, 704, 713, 804, 916))
    line = rng.randint(100, 199)
    style = rng.randint(0, 3)
    if style == 0:
        return f"({area}) 555-{line:04d}"
    if style == 1:
        return f"{area}-555-{line:04d}"
    if style == 2:
        return f"+1 {area} 555 {line:04d}"
    return f"{area}.555.{line:04d}"


def _phone_adversarial(rng: Random) -> tuple[str, str]:
    line = rng.randint(100, 199)
    choice = rng.choice(["area_lead", "area_n11", "exch_lead", "exch_n11"])
    if choice == "area_lead":
        bad_area = f"{rng.choice((0, 1))}{rng.randint(10, 99)}"
        return f"({bad_area}) 555-{line:04d}", "area code begins 0 or 1"
    if choice == "area_n11":
        return f"({rng.choice((2, 4, 6, 9))}11) 555-{line:04d}", "N11 service code as area code"
    if choice == "exch_lead":
        bad_exchange = f"{rng.choice((0, 1))}{rng.randint(10, 99)}"
        return f"(415) {bad_exchange}-{line:04d}", "exchange begins 0 or 1"
    return f"(415) {rng.choice((2, 4, 6, 9))}11-{line:04d}", "N11 service code as exchange"


def _email_valid(rng: Random, first: str = "", last: str = "") -> str:
    first = (first or rng.choice(("alex", "jordan", "sam", "riley", "casey"))).lower()
    last = (last or rng.choice(("nguyen", "delgado", "oconnor", "harper", "obrien"))).lower()
    local = rng.choice((f"{first}.{last}", f"{first[0]}{last}", f"{first}_{last}"))
    return f"{local}@{rng.choice(_EMAIL_DOMAINS)}"


def _email_adversarial(rng: Random) -> tuple[str, str]:
    domain = rng.choice(_EMAIL_DOMAINS)
    choice = rng.choice(["double_dot", "trailing_dot"])
    if choice == "double_dot":
        return f"a..borrower@{domain}", "consecutive dots in the local part"
    return f"borrower.@{domain}", "local part ends with a dot"


def _zip_valid(rng: Random) -> str:
    base = rng.randint(501, 99950)
    if rng.random() < 0.3:
        return f"{base:05d}-{rng.randint(1, 9999):04d}"
    return f"{base:05d}"


def _zip_adversarial(rng: Random) -> tuple[str, str]:
    if rng.random() < 0.5:
        return f"{rng.randint(0, 500):05d}", "below the assigned ZIP range"
    return f"{rng.randint(99951, 99999):05d}", "above the assigned ZIP range"


def _account_valid(rng: Random) -> str:
    length = rng.randint(8, 12)
    while True:
        value = "".join(str(rng.randint(0, 9)) for _ in range(length))
        if len(set(value)) > 2:
            return value


def _account_adversarial(rng: Random) -> tuple[str, str]:
    if rng.random() < 0.5:
        digit = str(rng.randint(0, 9))
        return digit * rng.randint(8, 12), "a single repeated digit is not an account number"
    start = rng.randint(0, 5)
    length = rng.randint(8, 9)
    run = "".join(str((start + i) % 10) for i in range(length))
    return run, "a sequential run is not an account number"


def _loan_valid(rng: Random) -> str:
    if rng.random() < 0.25:
        return rng.choice(("LN", "MT", "SVC")) + f"{rng.randrange(10 ** 8):08d}"
    return f"{rng.randrange(10 ** 10):010d}"


def _loan_adversarial(rng: Random) -> tuple[str, str]:
    digit = str(rng.randint(0, 9))
    return digit * 10, "a single repeated digit is not a loan number"


def _nmls_valid(rng: Random) -> str:
    return str(rng.randint(100000, 9999999))


def _nmls_adversarial(rng: Random) -> tuple[str, str]:
    if rng.random() < 0.5:
        return f"0{rng.randint(10000, 99999)}", "NMLS IDs are not zero padded"
    return str(rng.randint(1, 9)) * rng.randint(4, 7), "a single repeated digit is not an NMLS ID"


def _state_valid(rng: Random) -> str:
    return rng.choice(_STATE_NAMES)


def _state_abbrev(rng: Random) -> str:
    return rng.choice(_STATES)


def _state_adversarial(rng: Random) -> tuple[str, str]:
    return rng.choice(("XX", "ZZ", "QQ", "VV")), "shape-valid abbreviation, not an assigned state"


def _money_valid(rng: Random) -> str:
    amount = rng.choice([
        rng.randint(50, 999),
        rng.randint(1000, 9999),
        rng.randint(10000, 99999),
        rng.randint(100000, 899999),
    ])
    return f"${amount:,}.{rng.randint(0, 99):02d}"


def _money_adversarial(rng: Random) -> tuple[str, str]:
    if rng.random() < 0.5:
        return f"${rng.randint(1, 9)},{rng.randint(10, 99)}.{rng.randint(0, 99):02d}", (
            "malformed thousands grouping"
        )
    return f"${rng.randint(10, 999)}.{rng.randint(100, 999)}", "sub-cent precision"


# --------------------------------------------------------------------------
# tier 3 -- no validator, so no adversarial form
# --------------------------------------------------------------------------

_FIRST = ("Maria", "James", "Aisha", "Robert", "Linda", "Carlos", "Priya", "Daniel",
          "Fatima", "Michael", "Sofia", "Andre", "Grace", "Hector", "Nia", "Thomas")
_LAST = ("Delgado", "O'Connor", "Nguyen", "Whitfield", "Okafor", "Petrov", "Alvarez",
         "Brennan", "Castillo", "Mbeki", "Lindqvist", "Rahman", "Tanaka", "Ferreira")
_STREETS = ("Kingsley Terrace", "Oak Street", "Maple Avenue", "Sycamore Lane",
            "Harborview Drive", "Larkspur Road", "Chestnut Court", "Winslow Boulevard",
            "Kettle Creek Way", "Ashford Place")
_CITIES = ("Sacramento", "Fort Worth", "Tulsa", "Bridgeport", "Asheville", "Boise",
           "Springfield", "Rochester", "Chandler", "Savannah", "Albany", "Dayton")


def _person_valid(rng: Random) -> str:
    name = f"{rng.choice(_FIRST)} {rng.choice(_LAST)}"
    if rng.random() < 0.2:
        name = f"{name.split()[0]} {rng.choice('ABCDEFGHJKLMPRST')}. {name.split()[1]}"
    return name


def _street_valid(rng: Random) -> str:
    return f"{rng.randint(1, 9999)} {rng.choice(_STREETS)}"


def _city_valid(rng: Random) -> str:
    return rng.choice(_CITIES)


def _date_valid(rng: Random) -> str:
    return f"{rng.randint(1, 12):02d}/{rng.randint(1, 28):02d}/{rng.randint(2019, 2025)}"


def _credit_score_valid(rng: Random) -> str:
    return str(rng.randint(520, 820))


PROVIDERS: dict[str, Provider] = {
    "ssn": Provider(_ssn_valid, _ssn_adversarial),
    "aba_routing": Provider(_aba_valid, _aba_adversarial),
    "credit_card": Provider(_card_valid, _card_adversarial),
    "mers_min": Provider(_mers_valid, _mers_adversarial),
    "ein": Provider(_ein_valid, _ein_adversarial),
    "itin": Provider(_itin_valid, _itin_adversarial),
    "phone": Provider(_phone_valid, _phone_adversarial),
    "email": Provider(_email_valid, _email_adversarial),
    "zip_code": Provider(_zip_valid, _zip_adversarial),
    "us_account_num": Provider(_account_valid, _account_adversarial),
    "loan_number": Provider(_loan_valid, _loan_adversarial),
    "nmls_id": Provider(_nmls_valid, _nmls_adversarial),
    "us_state": Provider(_state_valid, _state_adversarial),
    "money": Provider(_money_valid, _money_adversarial),
    "person_name": Provider(_person_valid),
    "street_address": Provider(_street_valid),
    "city": Provider(_city_valid),
    "date": Provider(_date_valid),
    "credit_score": Provider(_credit_score_valid),
}

#: Servicing text that is numerically PII-shaped but is not PII. Without these
#: in the corpus, a precision number means very little: the easy way to score
#: well on synthetic data is to claim every digit run in sight.
#:
#: Grouped by category so templates can request one that fits the sentence.
#: An interest rate and a CFR citation are both distractors, but "the note rate
#: of 1024.35" reads as nonsense and a corpus that reads as nonsense is not
#: evidence of anything.
DISTRACTORS_BY_CATEGORY: dict[str, tuple[tuple[str, str], ...]] = {
    "rate": (
        ("6.875%", "interest rate"),
        ("4.250%", "interest rate"),
        ("7.125%", "interest rate"),
        ("5.500%", "interest rate"),
    ),
    "citation": (
        ("1026.41", "Regulation Z periodic statement citation"),
        ("1024.35", "RESPA notice of error citation"),
        ("1024.36", "RESPA request for information citation"),
        ("Section 6", "RESPA servicing section"),
        ("1024.41", "RESPA loss mitigation citation"),
    ),
    "form": (
        ("1003", "URLA form number"),
        ("203(k)", "FHA rehabilitation programme"),
        ("Form 4506-C", "IRS transcript request form"),
        ("HUD-1", "settlement statement form"),
        ("Form 1098", "mortgage interest statement"),
    ),
    "term": (
        ("360 months", "loan term"),
        ("480 months", "modified loan term"),
        ("12 monthly instalments", "shortage spread period"),
    ),
    "reference": (
        ("INV-2024-0098", "invoice reference"),
        ("CASE-2024-001847", "servicing case reference"),
        ("Batch 00471", "posting batch number"),
        ("Doc ID 55510412", "imaging system document id"),
        ("Tier 2", "internal workflow tier"),
        ("QUEUE-4471", "workflow queue reference"),
    ),
}

#: Flat view, for callers that do not care about category.
DISTRACTORS: tuple[tuple[str, str], ...] = tuple(
    item for group in DISTRACTORS_BY_CATEGORY.values() for item in group
)


def distractor(rng: Random, category: str | None = None) -> tuple[str, str]:
    """Pick a distractor, optionally from one category."""
    pool = DISTRACTORS if category is None else DISTRACTORS_BY_CATEGORY.get(category)
    if not pool:
        raise KeyError(
            f"unknown distractor category {category!r}; known categories are "
            f"{', '.join(sorted(DISTRACTORS_BY_CATEGORY))}"
        )
    return pool[rng.randrange(len(pool))]


def state_abbreviation(rng: Random) -> str:
    """Postal abbreviation, for the ``City, ST ZIP`` line of an address block."""
    return _state_abbrev(rng)


def email_for(rng: Random, full_name: str) -> str:
    """An address derived from a person's name, so documents read coherently."""
    parts = full_name.replace(".", "").split()
    return _email_valid(rng, parts[0], parts[-1])
