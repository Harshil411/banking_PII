"""Arbitration properties.

Arbitration is the piece with no library underneath it, and it is exactly
where v1 failed. So it is tested as a pure function over generated candidate
sets, before any detector is wired to it.

The four invariants that matter:

  non-overlapping   anonymisation replaces spans by offset; two surviving
                    spans over the same characters produce garbled output
  sorted            a stable contract for every consumer
  order-independent shuffling the detector output must not change the answer
  idempotent        re-arbitrating a settled result changes nothing

Order-independence is the one that catches real bugs. A greedy sweep that
depends on input order will pass every hand-written example and then diff
against a frozen evaluation set for reasons nobody can reproduce.
"""

from __future__ import annotations

import random

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.core.arbitration import arbitrate, validate
from app.core.taxonomy import load_taxonomy
from app.core.types import Candidate, Tier, ValidationStatus
from synth.providers import PROVIDERS

from .conftest import TAXONOMY_PATH

DOCUMENT = (
    "Loan 0012345678 for Maria Delgado at 88 Oak Street, Sacramento, CA 95814. "
    "SSN 457551275, routing 011000015, account 483920117, card 4111111111111111. "
    "Contact (415) 555-0142 or m.delgado@example.com about $1,204.55 due 03/15/2024."
)

TAXONOMY = load_taxonomy(TAXONOMY_PATH, known_generators=set(PROVIDERS))
TYPES = sorted(TAXONOMY.entities)


@st.composite
def candidate(draw) -> Candidate:
    start = draw(st.integers(min_value=0, max_value=len(DOCUMENT) - 2))
    length = draw(st.integers(min_value=1, max_value=min(24, len(DOCUMENT) - start)))
    return Candidate.from_span(
        document=DOCUMENT,
        entity_type=draw(st.sampled_from(TYPES)),
        start=start,
        end=start + length,
        score=draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False)),
        source=draw(st.sampled_from(["deterministic", "presidio"])),
    )


candidates = st.lists(candidate(), min_size=0, max_size=40)

SLOW = settings(max_examples=250, suppress_health_check=[HealthCheck.too_slow], deadline=None)


# --------------------------------------------------------------------------
# Invariants
# --------------------------------------------------------------------------


@given(candidates)
@SLOW
def test_kept_entities_never_overlap(items):
    kept, _ = arbitrate(items, TAXONOMY)
    for earlier, later in zip(kept, kept[1:], strict=False):
        assert earlier.end <= later.start, f"{earlier} overlaps {later}"


@given(candidates)
@SLOW
def test_kept_entities_are_sorted(items):
    kept, _ = arbitrate(items, TAXONOMY)
    assert kept == sorted(kept, key=lambda e: (e.start, e.end))


@given(candidates)
@SLOW
def test_arbitration_is_order_independent(items):
    """Shuffling detector output must not change the answer."""
    expected, _ = arbitrate(items, TAXONOMY)
    shuffled = list(items)
    random.Random(1234).shuffle(shuffled)
    actual, _ = arbitrate(shuffled, TAXONOMY)
    assert [(e.entity_type, e.start, e.end) for e in expected] == [
        (e.entity_type, e.start, e.end) for e in actual
    ]


@given(candidates)
@SLOW
def test_arbitration_is_idempotent(items):
    kept, _ = arbitrate(items, TAXONOMY)
    again, _ = arbitrate(
        [
            Candidate.from_span(DOCUMENT, e.entity_type, e.start, e.end, e.score, e.source)
            for e in kept
        ],
        TAXONOMY,
    )
    assert [(e.entity_type, e.start, e.end) for e in kept] == [
        (e.entity_type, e.start, e.end) for e in again
    ]


@given(candidates)
@SLOW
def test_every_candidate_is_accounted_for(items):
    """Nothing may vanish silently: each candidate is kept or explained."""
    kept, dropped = arbitrate(items, TAXONOMY)
    distinct_input = {(c.entity_type, c.start, c.end) for c in items}
    accounted = {(e.entity_type, e.start, e.end) for e in kept + dropped}
    assert distinct_input == accounted


@given(candidates)
@SLOW
def test_every_dropped_entity_carries_a_reason(items):
    _, dropped = arbitrate(items, TAXONOMY)
    for entity in dropped:
        assert entity.reason, f"{entity.entity_type} dropped with no explanation"


# --------------------------------------------------------------------------
# Precedence rules
# --------------------------------------------------------------------------


def _candidate(entity_type: str, start: int, end: int, score: float = 0.9) -> Candidate:
    return Candidate.from_span(DOCUMENT, entity_type, start, end, score, "test")


def test_tier_one_pass_beats_an_overlapping_lower_tier():
    span = DOCUMENT.index("011000015")
    kept, dropped = arbitrate(
        [
            _candidate("ABA_ROUTING", span, span + 9),
            _candidate("US_ACCOUNT_NUM", span, span + 9, score=1.0),
        ],
        TAXONOMY,
    )
    assert [e.entity_type for e in kept] == ["ABA_ROUTING"]
    assert dropped[0].entity_type == "US_ACCOUNT_NUM"
    assert "overlapped" in dropped[0].reason


def test_tier_one_pass_beats_a_higher_scored_tier_three():
    """Evidence class outranks confidence: arithmetic beats a 1.0 softmax."""
    span = DOCUMENT.index("011000015")
    kept, _ = arbitrate(
        [
            _candidate("ABA_ROUTING", span, span + 9, score=0.1),
            _candidate("PERSON_NAME", span, span + 9, score=1.0),
        ],
        TAXONOMY,
    )
    assert [e.entity_type for e in kept] == ["ABA_ROUTING"]


def test_tier_one_failure_does_not_shadow_a_weaker_reading():
    """A nine-digit run that fails the SSA rules is not an SSN.

    It may still be an account number, and suppressing that reading because a
    stronger type looked at the span first would lose a real entity.
    """
    span = DOCUMENT.index("483920117")
    kept, dropped = arbitrate(
        [
            _candidate("ABA_ROUTING", span, span + 9),  # fails the ABA checksum
            _candidate("US_ACCOUNT_NUM", span, span + 9),
        ],
        TAXONOMY,
    )
    assert [e.entity_type for e in kept] == ["US_ACCOUNT_NUM"]
    assert dropped[0].entity_type == "ABA_ROUTING"
    assert "checksum" in dropped[0].reason or "range" in dropped[0].reason


def test_failed_validation_is_reported_not_hidden():
    span = DOCUMENT.index("0012345678")
    _, dropped = arbitrate([_candidate("ABA_ROUTING", span, span + 9)], TAXONOMY)
    assert len(dropped) == 1
    assert dropped[0].validation_status is ValidationStatus.FAIL
    assert dropped[0].validator == "aba_routing"


def test_context_gated_type_beats_a_generic_one_in_the_same_tier():
    """"loan number 0012345678" is a loan number, not a ten-digit deposit account.

    LOAN_NUMBER and US_ACCOUNT_NUM are both tier 2 and both match the same
    span. The gated type is only ever emitted when a context word was found
    nearby, so it carries evidence the bare pattern match does not.
    """
    from app.detect.deterministic import DeterministicDetector

    text = "Remit against loan number 0012345678 before Friday."
    kept, dropped = arbitrate(DeterministicDetector(TAXONOMY).detect(text), TAXONOMY)
    labels = {e.entity_type for e in kept}
    assert "LOAN_NUMBER" in labels, f"expected LOAN_NUMBER, kept {labels}"
    assert "US_ACCOUNT_NUM" in {e.entity_type for e in dropped}


def test_generic_type_still_wins_without_context():
    """Without a loan-context word the gated type is never emitted at all."""
    from app.detect.deterministic import DeterministicDetector

    text = "Remit against reference 0012345678 before Friday."
    kept, _ = arbitrate(DeterministicDetector(TAXONOMY).detect(text), TAXONOMY)
    assert {e.entity_type for e in kept} == {"US_ACCOUNT_NUM"}


def test_longer_span_wins_within_a_tier():
    start = DOCUMENT.index("4111111111111111")
    kept, _ = arbitrate(
        [
            _candidate("CREDIT_CARD", start, start + 16),
            _candidate("US_ACCOUNT_NUM", start, start + 10),
        ],
        TAXONOMY,
    )
    assert [(e.entity_type, e.length) for e in kept] == [("CREDIT_CARD", 16)]


def test_partial_overlap_drops_the_loser_whole():
    """Spans are never truncated: half an account number is not a shorter entity."""
    start = DOCUMENT.index("483920117")
    kept, _ = arbitrate(
        [
            _candidate("US_ACCOUNT_NUM", start, start + 9),
            _candidate("ZIP", start + 4, start + 9),
        ],
        TAXONOMY,
    )
    assert len(kept) == 1
    assert (kept[0].start, kept[0].end) == (start, start + 9)


def test_identical_candidates_are_collapsed():
    span = DOCUMENT.index("011000015")
    kept, dropped = arbitrate(
        [_candidate("ABA_ROUTING", span, span + 9, 0.5)] * 3, TAXONOMY
    )
    assert len(kept) == 1 and not dropped


def test_empty_input():
    assert arbitrate([], TAXONOMY) == ([], [])


# --------------------------------------------------------------------------
# Validation status semantics
# --------------------------------------------------------------------------


def test_tier_three_is_not_applicable_never_pass():
    """Conflating NOT_APPLICABLE with PASS would make the drift ratio meaningless."""
    entity = validate(_candidate("PERSON_NAME", 20, 33), TAXONOMY)
    assert entity.validation_status is ValidationStatus.NOT_APPLICABLE
    assert entity.tier is Tier.CONTEXTUAL
    assert entity.validator is None


@pytest.mark.parametrize("entity_type", ["SSN", "ABA_ROUTING", "CREDIT_CARD", "MERS_MIN"])
def test_tier_one_types_always_produce_a_verdict(entity_type):
    entity = validate(_candidate(entity_type, 5, 15), TAXONOMY)
    assert entity.validation_status in (ValidationStatus.PASS, ValidationStatus.FAIL)
    assert entity.validator is not None
