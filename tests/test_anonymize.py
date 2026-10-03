"""Redaction behaviour, including the guard v1 did not have."""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.core.anonymize import (
    OverlappingSpansError,
    RedactionPolicy,
    _failed_tier1,
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

#: Dense with tier-1-shaped digit runs, so random spans fail validation often
#: and overlap kept entities often -- the case the over-redact policy must handle.
PROPERTY_DOCUMENT = (
    "SSN 666121234, routing 011000016, account 483920117, card 4111111111111112, "
    "MIN 100002300000000019, loan 0012345678, call (415) 555-0142 on 03/15/2024."
)
TYPES = sorted(TAXONOMY.entities)
SLOW = settings(max_examples=250, suppress_health_check=[HealthCheck.too_slow], deadline=None)


@st.composite
def _candidate(draw) -> Candidate:
    start = draw(st.integers(min_value=0, max_value=len(PROPERTY_DOCUMENT) - 2))
    length = draw(st.integers(min_value=1, max_value=min(24, len(PROPERTY_DOCUMENT) - start)))
    return Candidate.from_span(
        document=PROPERTY_DOCUMENT,
        entity_type=draw(st.sampled_from(TYPES)),
        start=start,
        end=start + length,
        score=draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False)),
        source="test",
    )


candidates = st.lists(_candidate(), min_size=0, max_size=40)


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


def test_failed_tier_one_under_a_kept_span_is_redacted_once_and_unmasked():
    """The common case, and it used to be a 500.

    Arbitration rule 2 takes a failed SSN out of contention so an account
    number can claim the same digits. Both then reached the overlap guard.
    The account's type labels the result, but its usual last-four mask is
    dropped: those four digits are also four digits of a possibly mistyped
    SSN, and the over-redact policy exists not to show them.
    """
    text = "Taxpayer SSN, credit to account 666121234 today."
    kept, dropped = arbitrate(DETECTOR.detect(text), TAXONOMY)
    assert [e.entity_type for e in kept] == ["US_ACCOUNT_NUM"]
    assert any(e.entity_type == "SSN" and e.validation_status is ValidationStatus.FAIL
               for e in dropped)

    over = anonymize(text, kept, RedactionPolicy(redact_failed_tier1=True), dropped=dropped)
    assert over == "Taxpayer SSN, credit to account [ACCOUNT] today."
    assert anonymize(text, kept, dropped=dropped) == (
        "Taxpayer SSN, credit to account *****1234 today."
    )


def test_two_failed_tier_one_readings_of_one_span_redact_once():
    """One nine-digit string can fail SSN and ABA_ROUTING at once; they overlap each other.

    Neither reading was accepted, so neither label is asserted.
    """
    text = "Reference 666121234 in the file."
    dropped = [
        _entity("SSN", 10, 19, "666121234", Tier.ARITHMETIC, ValidationStatus.FAIL),
        _entity("ABA_ROUTING", 10, 19, "666121234", Tier.ARITHMETIC, ValidationStatus.FAIL),
    ]
    redacted = anonymize(text, [], RedactionPolicy(redact_failed_tier1=True), dropped=dropped)
    assert redacted == "Reference [REDACTED] in the file."


def test_a_partial_overlap_is_merged_so_no_digit_survives():
    """Skipping the failed span would leave its uncovered digits in the output.

    The region is not masked -- its last four characters belong to the
    rejected span -- and is not labelled ACCOUNT, because its tail is not.
    """
    text = "ref 4839201175555 end"
    kept = [_entity("US_ACCOUNT_NUM", 4, 13, "483920117")]
    dropped = [_entity("SSN", 8, 17, "201175555", Tier.ARITHMETIC, ValidationStatus.FAIL)]
    redacted = anonymize(text, kept, RedactionPolicy(redact_failed_tier1=True), dropped=dropped)
    assert redacted == "ref [REDACTED] end"


def test_a_failed_span_bridging_two_kept_entities_merges_all_three():
    """Two ZIPs and the SSN-shaped characters between them are not one ZIP."""
    text = "x 12345 67890 y"
    kept = [_entity("ZIP", 2, 7, "12345"), _entity("ZIP", 8, 13, "67890")]
    dropped = [_entity("SSN", 4, 11, "345 678", Tier.ARITHMETIC, ValidationStatus.FAIL)]
    redacted = anonymize(text, kept, RedactionPolicy(redact_failed_tier1=True), dropped=dropped)
    assert redacted == "x [REDACTED] y"


def test_a_merged_region_of_mixed_kept_types_names_neither():
    """Labelling it with the first type would silently drop the second."""
    text = "x 12345 (415) 555-0142 y"
    kept = [_entity("ZIP", 2, 7, "12345"), _entity("PHONE", 8, 22, "(415) 555-0142")]
    dropped = [_entity("SSN", 4, 12, "345 (415", Tier.ARITHMETIC, ValidationStatus.FAIL)]
    redacted = anonymize(text, kept, RedactionPolicy(redact_failed_tier1=True), dropped=dropped)
    assert redacted == "x [REDACTED] y"


def test_a_lone_failed_reading_is_never_masked():
    """A Luhn-failing card shows no digits, whether one reading or two."""
    text = "card 4111111111111112 on file"
    card = _entity("CREDIT_CARD", 5, 21, "4111111111111112", Tier.ARITHMETIC,
                   ValidationStatus.FAIL)
    policy = RedactionPolicy(redact_failed_tier1=True)
    assert anonymize(text, [], policy, dropped=[card]) == "card [CARD] on file"
    assert anonymize(text, [], policy, dropped=[card, card]) == "card [CARD] on file"


def test_a_failed_reading_inside_a_kept_entity_takes_the_kept_label():
    """The kept entity spans the whole region, so its type is true of every character."""
    text = "ref 1234566661212 end"
    kept = [_entity("US_ACCOUNT_NUM", 4, 17, "1234566661212")]
    dropped = [_entity("SSN", 6, 15, "345666121", Tier.ARITHMETIC, ValidationStatus.FAIL)]
    redacted = anonymize(text, kept, RedactionPolicy(redact_failed_tier1=True), dropped=dropped)
    assert redacted == "ref [ACCOUNT] end"


def test_the_overlap_guard_still_applies_to_arbitration_output_under_the_flag():
    """The exemption covers the failed spans the flag adds, not the caller's entities."""
    text = "account 483920117 recorded"
    entities = [
        _entity("US_ACCOUNT_NUM", 8, 17, "483920117"),
        _entity("SSN", 12, 17, "20117", Tier.ARITHMETIC),
    ]
    with pytest.raises(OverlappingSpansError):
        anonymize(text, entities, RedactionPolicy(redact_failed_tier1=True))


@given(candidates)
@SLOW
def test_over_redaction_never_raises_and_covers_every_target(cands):
    """Every character of every kept or failed tier-1 span is gone; nothing else is.

    Each region is replaced by "#", which the document does not contain, so
    deleting the markers must leave exactly the characters no target touched.
    """
    kept, dropped = arbitrate(cands, TAXONOMY)
    policy = RedactionPolicy(
        default_token="#", tokens={}, mask_last_four=frozenset(), redact_failed_tier1=True
    )
    redacted = anonymize(PROPERTY_DOCUMENT, kept, policy, dropped=dropped)

    targets = kept + _failed_tier1(dropped)
    covered = {i for e in targets for i in range(e.start, e.end)}
    untouched = "".join(c for i, c in enumerate(PROPERTY_DOCUMENT) if i not in covered)
    assert redacted.replace("#", "") == untouched


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
