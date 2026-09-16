"""Core value types shared by detection, validation, arbitration and the API.

These are plain frozen dataclasses rather than Pydantic models on purpose:
they sit on the hot path and are constructed per-candidate per-document.
Pydantic is used at the API boundary (``app/api/schemas.py``), where
validation of untrusted input is the point.

The invariant that matters most in this module is stated once, in
:meth:`Candidate.from_span`, and enforced there: a candidate's ``text`` is
always a slice of the source document, never a detector's own rendering of
it. v1 trusted the tokenizer's ``word`` field and inherited its ``##``
subword artifacts, which silently broke email and other multi-token spans.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum, IntEnum


class Tier(IntEnum):
    """Strength of evidence that a span is a true instance of its type.

    This describes the *evidence*, not the mechanism that produced the
    candidate: a tier-3 entity may come from a regex, and a tier-2 entity may
    come from a model.
    """

    ARITHMETIC = 1
    STRUCTURAL = 2
    CONTEXTUAL = 3


class ValidationStatus(str, Enum):
    """Outcome of running a type's validator against a candidate.

    ``NOT_APPLICABLE`` is deliberately distinct from ``PASS``. A tier-3
    entity has no validator and can never be said to have passed one;
    collapsing the two would make "share of entities that survived
    validation" meaningless, and that ratio is the drift signal this design
    exists to produce.
    """

    PASS = "pass"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"


class ValueKind(str, Enum):
    """Why a value was placed in a synthetic document.

    Recorded per gold span at generation time. It cannot be recovered
    afterwards, and without it the headline claim of this project -- what
    share of regex-passing near-misses the validators reject -- is not
    computable.
    """

    VALID = "valid"
    ADVERSARIAL = "adversarial"
    DISTRACTOR = "distractor"


@dataclass(frozen=True, slots=True)
class Candidate:
    """A proposed entity span, before validation and arbitration."""

    entity_type: str
    start: int
    end: int
    text: str
    score: float
    source: str
    pattern_name: str | None = None

    @classmethod
    def from_span(
        cls,
        document: str,
        entity_type: str,
        start: int,
        end: int,
        score: float,
        source: str,
        pattern_name: str | None = None,
    ) -> Candidate:
        """Build a candidate by slicing ``document``.

        This is the only supported constructor for detector output. Detectors
        report offsets; the text always comes from the source document.
        """
        if not 0 <= start < end <= len(document):
            raise ValueError(
                f"span ({start}, {end}) is not within a document of length {len(document)}"
            )
        return cls(
            entity_type=entity_type,
            start=start,
            end=end,
            text=document[start:end],
            score=score,
            source=source,
            pattern_name=pattern_name,
        )

    def overlaps(self, other: Candidate | Entity) -> bool:
        return self.start < other.end and other.start < self.end

    @property
    def length(self) -> int:
        return self.end - self.start


@dataclass(frozen=True, slots=True)
class Entity:
    """A candidate that has been validated and has survived arbitration."""

    entity_type: str
    start: int
    end: int
    text: str
    score: float
    source: str
    tier: Tier
    validation_status: ValidationStatus
    validator: str | None = None
    reason: str = ""
    pattern_name: str | None = None

    @classmethod
    def from_candidate(
        cls,
        candidate: Candidate,
        tier: Tier,
        validation_status: ValidationStatus,
        validator: str | None = None,
        reason: str = "",
    ) -> Entity:
        return cls(
            entity_type=candidate.entity_type,
            start=candidate.start,
            end=candidate.end,
            text=candidate.text,
            score=candidate.score,
            source=candidate.source,
            tier=tier,
            validation_status=validation_status,
            validator=validator,
            reason=reason,
            pattern_name=candidate.pattern_name,
        )

    def overlaps(self, other: Candidate | Entity) -> bool:
        return self.start < other.end and other.start < self.end

    def relabelled(self, entity_type: str) -> Entity:
        return replace(self, entity_type=entity_type)

    @property
    def length(self) -> int:
        return self.end - self.start


@dataclass(frozen=True, slots=True)
class GoldSpan:
    """A ground-truth span emitted by the synthetic generator.

    Offsets are recorded as the document is constructed, never recovered by
    searching the finished text -- a borrower's name appears in the header
    and again in the body, and ``str.find`` returns the wrong one.

    ``entity_type`` is ``None`` for distractors: they are servicing text that
    is PII-shaped but is not PII, so they belong to no type. They are recorded
    with offsets anyway, because a precision number is only meaningful if the
    corpus contains things a detector ought to leave alone.
    """

    entity_type: str | None
    start: int
    end: int
    text: str
    tier: int | None
    value_kind: ValueKind
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "entity_type": self.entity_type,
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "tier": self.tier,
            "value_kind": self.value_kind.value,
            "note": self.note,
        }
