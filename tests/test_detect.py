"""Detector behaviour: context gating, and keeping Presidio's stock output out."""

from __future__ import annotations

import pytest

from app.core.arbitration import arbitrate
from app.core.taxonomy import load_taxonomy
from app.detect.deterministic import DeterministicDetector
from app.detect.registry import build_detector
from synth.providers import PROVIDERS

from .conftest import TAXONOMY_PATH

TAXONOMY = load_taxonomy(TAXONOMY_PATH, known_generators=set(PROVIDERS))
DETERMINISTIC = DeterministicDetector(TAXONOMY)


def _labels(text: str, detector=DETERMINISTIC) -> dict[str, str]:
    kept, _ = arbitrate(detector.detect(text), TAXONOMY)
    return {e.text: e.entity_type for e in kept}


# --------------------------------------------------------------------------
# Context gating
# --------------------------------------------------------------------------


def test_gated_type_is_not_emitted_without_context():
    assert "NMLS_ID" not in _labels("Batch 167890 completed.").values()
    assert _labels("Originator NMLS 167890 on file.") == {"167890": "NMLS_ID"}


def test_context_words_match_on_word_boundaries():
    """"tin" must not match inside "institution".

    This was a real defect: "receiving institution routing number is ..." is
    the sentence a routing number appears in, so substring matching gated SSN
    in beside every wire instruction. Being tier 1, SSN then won the span and
    ABA_ROUTING recall fell to 0.022.
    """
    text = "The receiving institution routing number is 011000015 for wires."
    assert _labels(text) == {"011000015": "ABA_ROUTING"}


def test_nearest_context_word_decides_between_gated_types():
    assert _labels("Remit against loan number 0012345678 today.") == {
        "0012345678": "LOAN_NUMBER"
    }
    assert _labels("Credit to account: 169340608835 for the loan number above.") == {
        "169340608835": "US_ACCOUNT_NUM"
    }


def test_context_window_does_not_reach_the_next_field():
    """A context word two clauses away must not vouch for a span."""
    text = "Promise to pay recorded for 10/13/2021. Escalated to contact, NMLS 1674329."
    labels = _labels(text)
    assert labels.get("10/13/2021") == "DATE", "the year was claimed as an NMLS id"
    assert labels.get("1674329") == "NMLS_ID"


def test_longer_span_beats_a_nested_gated_one():
    """NMLS_ID's 4-7 digit pattern matches the tail of an EIN."""
    text = "The taxpayer identification number is 20-7746014 and NMLS is 1674329."
    labels = _labels(text)
    assert labels.get("20-7746014") == "EIN"


def test_candidate_text_always_matches_the_source_document():
    text = "Wire to routing 011000015 credit account 483920117 for loan 0012345678."
    for candidate in DETERMINISTIC.detect(text):
        assert candidate.text == text[candidate.start : candidate.end]


def test_deterministic_detector_never_emits_model_carried_types():
    text = "Maria Delgado of Sacramento called."
    assert not {c.entity_type for c in DETERMINISTIC.detect(text)} & {"PERSON_NAME", "CITY"}


def test_entity_type_filter_is_respected():
    text = "SSN 457551275 and routing 011000015."
    types = {c.entity_type for c in DETERMINISTIC.detect(text, entity_types={"SSN"})}
    assert types <= {"SSN"}


# --------------------------------------------------------------------------
# Presidio: candidate generation only
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def presidio():
    detector = build_detector("presidio", TAXONOMY)
    detector.warm()
    return detector


@pytest.mark.slow
def test_presidio_native_recognizers_never_reach_arbitration(presidio):
    """The registry is trimmed to spaCy NER, and this is what that buys.

    Presidio's stock output on this sentence includes US_SSN at 0.4 with no
    SSA arithmetic behind it, US_BANK_NUMBER and US_PASSPORT at 0.05 on the
    same nine digits, DATE_TIME over a credit card number, and ORGANIZATION
    over the literal word "SSN". Admitting any of it would move precision for
    reasons that look like a model regression.
    """
    text = "Maria Delgado called about SSN 457551275 and card 4111111111111111."
    candidates = presidio.detect(text)

    produced = {c.entity_type for c in candidates}
    assert produced <= set(TAXONOMY.entities), f"unmapped types leaked: {produced}"

    from_presidio = {c.entity_type for c in candidates if c.source == "presidio"}
    assert from_presidio <= {"PERSON_NAME", "CITY", "US_STATE"}, (
        f"a stock recognizer has crept back in: {from_presidio}"
    )


@pytest.mark.slow
def test_presidio_supplies_the_model_carried_types(presidio):
    labels = _labels("Maria Delgado of Sacramento, CA 95814 called.", presidio)
    assert labels.get("Maria Delgado") == "PERSON_NAME"
    assert labels.get("Sacramento") == "CITY"


@pytest.mark.slow
def test_location_is_split_into_city_and_state(presidio):
    """spaCy labels both as GPE; the closed-set check disambiguates."""
    labels = _labels("Property in Sacramento, California is current.", presidio)
    assert labels.get("Sacramento") == "CITY"
    assert labels.get("California") == "US_STATE"


@pytest.mark.slow
def test_spans_are_trimmed_of_trailing_punctuation(presidio):
    for candidate in presidio.detect("Contact Maria Delgado, the borrower."):
        assert candidate.text == candidate.text.strip(" .,;:")


@pytest.mark.slow
def test_model_spans_do_not_cross_a_line_break(presidio):
    """spaCy runs PERSON spans into the next field of a structured document.

    In a payoff statement the PERSON span covered "Maria Delgado\nLoan", so
    redaction ate the word "Loan" out of the following label. Truncating
    model-carried spans at the first newline took PERSON_NAME from F1 0.748 to
    0.947 and overall micro-F1 from 0.948 to 0.974.
    """
    text = "Prepared for: Maria Delgado\nLoan number: 0012345678\n"
    for candidate in presidio.detect(text):
        assert "\n" not in candidate.text, f"{candidate.entity_type} span crosses a line break"

    kept, _ = arbitrate(presidio.detect(text), TAXONOMY)
    assert any(e.entity_type == "PERSON_NAME" and e.text == "Maria Delgado" for e in kept)


@pytest.mark.slow
def test_warm_is_idempotent(presidio):
    presidio.warm()
    presidio.warm()
    assert presidio.detect("Maria Delgado called.")
