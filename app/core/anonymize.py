"""Replacing entity spans in the source text.

Two things matter here, and v1 got one of them right.

Right: replacement must not invalidate offsets. v1 edited the string in place,
back to front, because replacing left to right shifts every later offset --
the replacement token is rarely the same length as what it replaced. This
version never edits: it assembles the output from slices of the untouched
original in one forward pass, which is both offset-safe and linear.

Missing: an overlap guard. v1's merge step let two overlapping spans with
different labels both survive, and this function then replaced both, producing
interleaved nonsense -- silently, with no error and no sign in the output that
anything had gone wrong. Overlapping *entities* are a programming error
upstream, so this raises rather than guessing. The one deliberate exception is
the failed tier-1 spans an over-redacting policy adds: those overlap
arbitration's output by design, and are merged into regions (``_regions``).

The policy layer exists because "redact everything to [REDACTED]" is not what
servicers actually do. An account number masked to its last four digits is
still useful to a human reading the file, and still not an account number.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from app.core.arbitration import is_rejection
from app.core.types import Entity, Tier, ValidationStatus


class OverlappingSpansError(ValueError):
    """Raised when asked to redact spans that overlap.

    Never expected in normal operation: arbitration guarantees its output is
    pairwise non-overlapping. Reaching this means a caller bypassed it. Failed
    tier-1 spans added by ``redact_failed_tier1`` are exempt -- they overlap
    arbitration output by design, and are merged instead (see ``_regions``).
    """


#: Per-type replacement tokens. A typed placeholder keeps the document
#: readable and tells a downstream reader what was removed.
DEFAULT_TOKENS: dict[str, str] = {
    "SSN": "[SSN]",
    "ITIN": "[ITIN]",
    "EIN": "[EIN]",
    "ABA_ROUTING": "[ROUTING]",
    "CREDIT_CARD": "[CARD]",
    "MERS_MIN": "[MIN]",
    "US_ACCOUNT_NUM": "[ACCOUNT]",
    "LOAN_NUMBER": "[LOAN]",
    "NMLS_ID": "[NMLS]",
    "PERSON_NAME": "[NAME]",
    "STREET_ADDRESS": "[ADDRESS]",
    "CITY": "[CITY]",
    "US_STATE": "[STATE]",
    "ZIP": "[ZIP]",
    "PHONE": "[PHONE]",
    "EMAIL": "[EMAIL]",
    "DATE": "[DATE]",
    "MONEY": "[AMOUNT]",
    "CREDIT_SCORE": "[SCORE]",
}

#: Types masked to their last four characters rather than replaced outright.
DEFAULT_MASKED: frozenset[str] = frozenset({"US_ACCOUNT_NUM", "CREDIT_CARD", "LOAN_NUMBER"})


@dataclass(frozen=True, slots=True)
class RedactionPolicy:
    """How each entity type is rewritten."""

    default_token: str = "[REDACTED]"
    tokens: Mapping[str, str] = field(default_factory=lambda: dict(DEFAULT_TOKENS))
    mask_last_four: frozenset[str] = DEFAULT_MASKED

    #: Whether to redact spans a tier-1 validator rejected.
    #:
    #: Defaults to False, and that choice deserves stating plainly rather than
    #: waiting to be challenged. When a validator proves a nine-digit string is
    #: not a valid SSN, keeping it means redacting text we have positive
    #: evidence is not the entity -- which is the false-positive behaviour this
    #: whole design exists to avoid. The cost is real: a genuine SSN mistyped
    #: by one digit stays in the output. Deployments that would rather over-
    #: redact than under-redact should set this True, and a privacy pipeline
    #: handling real borrower files probably should.
    redact_failed_tier1: bool = False

    def token_for(self, entity: Entity) -> str:
        if entity.entity_type in self.mask_last_four:
            return _mask_last_four(entity.text)
        return self.tokens.get(entity.entity_type, self.default_token)


def _mask_last_four(text: str) -> str:
    significant = [c for c in text if c.isalnum()]
    if len(significant) <= 4:
        return "*" * len(significant)
    return "*" * (len(significant) - 4) + "".join(significant[-4:])


def assert_non_overlapping(entities: list[Entity]) -> None:
    ordered = sorted(entities, key=lambda e: (e.start, e.end))
    for earlier, later in zip(ordered, ordered[1:], strict=False):
        if earlier.end > later.start:
            raise OverlappingSpansError(
                f"{earlier.entity_type} ({earlier.start}, {earlier.end}) overlaps "
                f"{later.entity_type} ({later.start}, {later.end}); redacting both would "
                "corrupt the output"
            )


def _failed_tier1(dropped: list[Entity]) -> list[Entity]:
    """The readings ``redact_failed_tier1`` adds: tier-1 failures, not fragments.

    A fragment lies strictly inside a longer validated match that was kept.
    It is an artefact of the shorter pattern, not a reading of the document:
    the characters are part of that longer value, so the container's own
    rendering -- last-four mask included -- is the right one for them. (A
    failed fragment whose containers all lost is reported by arbitration as
    an ordinary rejection, and is included.)
    """
    return [e for e in dropped if e.tier is Tier.ARITHMETIC and is_rejection(e)]


def _regions(entities: list[Entity], extra: list[Entity]) -> list[tuple[int, int, list[Entity]]]:
    """Group redaction targets into non-overlapping ``(start, end, members)``, in order.

    ``entities`` come from arbitration and never overlap each other. ``extra``
    -- the failed tier-1 spans an over-redacting policy adds -- routinely
    overlaps them, and that is by design rather than by accident: arbitration
    rule 2 takes a failed SSN out of contention precisely so that an account
    number may claim the same digits. Feeding both to the overlap guard is
    what made ``redact_failed_tier1=True`` return a 500 on ordinary input.

    So overlapping targets are swept into one region covering their union.
    Skipping a failed span that only partly overlaps would leave its
    uncovered digits in the output, under the one policy whose purpose is to
    never do that.
    """
    regions: list[tuple[int, int, list[Entity]]] = []
    for target in sorted([*entities, *extra], key=lambda e: (e.start, e.end, e.entity_type)):
        if regions and target.start < regions[-1][1]:
            start, end, members = regions[-1]
            members.append(target)
            regions[-1] = (start, max(end, target.end), members)
        else:
            regions.append((target.start, target.end, [target]))
    return regions


def _region_token(start: int, end: int, region: list[Entity], policy: RedactionPolicy) -> str:
    """The replacement for one region.

    Only a region that is exactly one kept entity is rewritten as it would be
    without the over-redact policy, last-four masking included. Any region
    holding a rejected reading is never masked: its last four characters
    belong, or may belong, to a span a validator rejected in its own right
    (a fragment of a kept value is not one; see ``_failed_tier1``) -- a mistyped SSN under an
    account number's mask is still four digits of an SSN, and a Luhn-failing
    card is still four digits of whatever it really is.

    A token names a type for every character it replaces, so a region gets a
    typed token only when that is true of the whole region:

    - a kept entity spanning the entire region names it, whatever failed
      readings lie inside it -- arbitration's answer for those characters
      outranks a rejected one;
    - otherwise, if every member is one type, that type names it;
    - otherwise the generic token. A failed SSN running past the end of a
      kept address is not an address, and a ZIP and a phone number bridged by
      a failed span are not one ZIP.
    """
    kept = [m for m in region if m.validation_status is not ValidationStatus.FAIL]
    if len(region) == 1 and kept:
        return policy.token_for(region[0])
    spanning = {m.entity_type for m in kept if m.start == start and m.end == end}
    types = spanning or {m.entity_type for m in region}
    if len(types) == 1:
        return policy.tokens.get(types.pop(), policy.default_token)
    return policy.default_token


def anonymize(
    text: str,
    entities: list[Entity],
    policy: RedactionPolicy | None = None,
    dropped: list[Entity] | None = None,
) -> str:
    """Return ``text`` with every entity span replaced according to ``policy``.

    ``entities`` must be arbitration output and is checked for overlap.
    ``dropped`` is consulted only when the policy redacts failed tier-1 spans;
    those may overlap ``entities`` and are merged into regions rather than rejected.
    """
    policy = policy or RedactionPolicy()

    assert_non_overlapping(entities)
    extra = _failed_tier1(dropped) if policy.redact_failed_tier1 and dropped else []
    if not entities and not extra:
        return text

    # Assembled in one forward pass from slices of the original. Every offset
    # indexes ``text``, which is never modified, so order cannot invalidate
    # an offset -- and one join is linear where rebuilding the string per
    # region was not.
    pieces: list[str] = []
    cursor = 0
    for start, end, members in _regions(entities, extra):
        pieces += [text[cursor:start], _region_token(start, end, members, policy)]
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)
