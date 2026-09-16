"""Redaction behaviour, including the guard v1 did not have."""

from __future__ import annotations

import pytest

from app.core.anonymize import (
    OverlappingSpansError,
    RedactionPolicy,
    anonymize,
    assert_non_overlapping,
)
from app.core.arbitration import arbitrate
from app.core.taxonomy import load_taxonomy
from app.core.types import Candidate, Entity, Tier, ValidationStatus
from app.detect.deterministic import DeterministicDetector
from synth.providers import PROVIDERS

from .conftest import TAXONOMY_PATH

TAXONOMY = load_taxonomy(TAXONOMY_PATH, known_generators=set(PROVIDERS))
DETECTOR = DeterministicDetector(TAXONOMY)


def _entity(entity_type, start, end, text, tier=Tier.STRUCTURAL, status=ValidationStatus.PASS):
    return Entity(
        entity_type=entity_type, start=start, end=end, text=text, score=1.0,
        source="test", tier=tier, validation_status=status,
    )


def test_replacement_runs_back_to_front():
    """Left-to-right replacement invalidates every later offset."""
    text = "SSN 457551275 and card 4111111111111111 on file."
    entities = [
        _entity("SSN", 4, 13, "457551275", Tier.ARITHMETIC),
        _entity("CREDIT_CARD", 23, 39, "4111111111111111", Tier.ARITHMETIC),
    ]
    assert anonymize(text, entities) == "SSN [SSN] and card ************1111 on file."


def test_overlapping_spans_raise_rather_than_corrupt():
    """v1 produced interleaved nonsense here, silently."""
    text = "account 483920117 recorded"
    entities = [
        _entity("US_ACCOUNT_NUM", 8, 17, "483920117"),
        _entity("SSN", 12, 17, "20117", Tier.ARITHMETIC),
    ]
    with pytest.raises(OverlappingSpansError, match="corrupt"):
        anonymize(text, entities)


def test_adjacent_spans_are_not_overlapping():
    assert_non_overlapping([_entity("ZIP", 0, 5, "95814"), _entity("CITY", 5, 13, "Savannah")])


def test_masking_keeps_the_last_four():
    text = "account 483920117 recorded"
    assert anonymize(text, [_entity("US_ACCOUNT_NUM", 8, 17, "483920117")]) == (
        "account *****0117 recorded"
    )


def test_masking_handles_separators():
    text = "card 4111 1111 1111 1111 on file"
    entities = [_entity("CREDIT_CARD", 5, 24, "4111 1111 1111 1111", Tier.ARITHMETIC)]
    assert anonymize(text, entities) == "card ************1111 on file"


def test_masking_short_values_reveals_nothing():
    assert anonymize("id 1234 here", [_entity("US_ACCOUNT_NUM", 3, 7, "1234")]) == "id **** here"


def test_unknown_type_uses_the_default_token():
    policy = RedactionPolicy(tokens={})
    assert anonymize("x 457551275 y", [_entity("SSN", 2, 11, "457551275")], policy) == (
        "x [REDACTED] y"
    )


def test_empty_entity_list_returns_the_original():
    assert anonymize("nothing here", []) == "nothing here"


# --------------------------------------------------------------------------
# The policy question worth volunteering before it is asked
# --------------------------------------------------------------------------


def test_failed_tier_one_is_left_in_place_by_default():
    """A proven non-SSN is not redacted, because redacting it is the false positive."""
    text = "Reference 666121234 in the file."
    dropped = [_entity("SSN", 10, 19, "666121234", Tier.ARITHMETIC, ValidationStatus.FAIL)]
    assert anonymize(text, [], dropped=dropped) == text


def test_failed_tier_one_can_be_redacted_when_the_deployment_prefers_it():
    text = "Reference 666121234 in the file."
    dropped = [_entity("SSN", 10, 19, "666121234", Tier.ARITHMETIC, ValidationStatus.FAIL)]
    policy = RedactionPolicy(redact_failed_tier1=True)
    assert anonymize(text, [], policy, dropped=dropped) == "Reference [SSN] in the file."


def test_failed_tier_two_is_never_force_redacted():
    """The flag is deliberately tier-1 only: arithmetic proof, not a shape rule."""
    text = "Reference 00-1234567 in the file."
    dropped = [_entity("EIN", 10, 20, "00-1234567", Tier.STRUCTURAL, ValidationStatus.FAIL)]
    assert anonymize(text, [], RedactionPolicy(redact_failed_tier1=True), dropped=dropped) == text


# --------------------------------------------------------------------------
# End to end against the real pipeline output
# --------------------------------------------------------------------------


def test_arbitration_output_is_always_safe_to_redact():
    """The contract between the two modules: arbitration guarantees no overlaps."""
    text = (
        "Loan 0012345678, MIN 100002300000000018, SSN 457551275, routing 011000015, "
        "account 483920117, card 4111 1111 1111 1111, call (415) 555-0142, "
        "email m.delgado@example.com, due 03/15/2024 for $1,204.55 at 88 Oak Street, "
        "Sacramento, CA 95814."
    )
    kept, dropped = arbitrate(DETECTOR.detect(text), TAXONOMY)
    redacted = anonymize(text, kept, dropped=dropped)
    for entity in kept:
        assert entity.text not in redacted, f"{entity.entity_type} {entity.text!r} survived"


def test_redaction_preserves_surrounding_text():
    text = "Please call (415) 555-0142 before Friday."
    kept, _ = arbitrate(DETECTOR.detect(text), TAXONOMY)
    redacted = anonymize(text, kept)
    assert redacted.startswith("Please call ") and redacted.endswith(" before Friday.")


def test_offsets_stay_valid_for_many_entities():
    """Regression guard for offset drift with a large number of replacements."""
    text = " ".join(f"account {i:09d}17" for i in range(40))
    candidates = [c for c in DETECTOR.detect(text) if c.entity_type == "US_ACCOUNT_NUM"]
    kept, dropped = arbitrate(candidates, TAXONOMY)
    redacted = anonymize(text, kept, dropped=dropped)
    assert redacted.count("*") >= 7 * len(kept)
    assert "account" in redacted


def test_candidate_text_always_matches_the_document():
    """The invariant that makes offset arithmetic trustworthy."""
    text = "SSN 457551275 on file"
    for candidate in DETECTOR.detect(text):
        assert isinstance(candidate, Candidate)
        assert candidate.text == text[candidate.start : candidate.end]
