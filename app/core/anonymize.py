"""Replacing entity spans in the source text.

Two things matter here, and v1 got one of them right.

Right: replacement runs back to front. Replacing left to right invalidates
every offset after the first substitution, because the replacement token is
rarely the same length as what it replaced.

Missing: an overlap guard. v1's merge step let two overlapping spans with
different labels both survive, and this function then replaced both, producing
interleaved nonsense -- silently, with no error and no sign in the output that
anything had gone wrong. Overlapping spans are a programming error upstream,
so this raises rather than guessing.

The policy layer exists because "redact everything to [REDACTED]" is not what
servicers actually do. An account number masked to its last four digits is
still useful to a human reading the file, and still not an account number.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from app.core.types import Entity, Tier, ValidationStatus


class OverlappingSpansError(ValueError):
    """Raised when asked to redact spans that overlap.

    Never expected in normal operation: arbitration guarantees its output is
    pairwise non-overlapping. Reaching this means a caller bypassed it.
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


def anonymize(
    text: str,
    entities: list[Entity],
    policy: RedactionPolicy | None = None,
    dropped: list[Entity] | None = None,
) -> str:
    """Return ``text`` with every entity span replaced according to ``policy``."""
    policy = policy or RedactionPolicy()

    targets = list(entities)
    if policy.redact_failed_tier1 and dropped:
        targets += [
            e
            for e in dropped
            if e.tier is Tier.ARITHMETIC and e.validation_status is ValidationStatus.FAIL
        ]

    if not targets:
        return text

    assert_non_overlapping(targets)

    result = text
    for entity in sorted(targets, key=lambda e: e.start, reverse=True):
        result = result[: entity.start] + policy.token_for(entity) + result[entity.end :]
    return result
