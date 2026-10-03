"""Pipeline orchestration and the instrumentation the later work depends on."""

from __future__ import annotations

import json

import pytest

from app.core.arbitration import is_fragment
from app.core.pipeline import Pipeline
from app.core.taxonomy import load_taxonomy
from app.core.types import ValidationStatus
from app.detect.registry import build_detector
from synth.providers import PROVIDERS

from .conftest import REPO_ROOT, TAXONOMY_PATH

TAXONOMY = load_taxonomy(TAXONOMY_PATH, known_generators=set(PROVIDERS))
SAMPLE = (
    "RE: Loan Number 0012345678, MIN 100002300000000018.\n"
    "Borrower verified with SSN 457551275. Wire to routing number 011000015, "
    "credit account 483920117. Contact (415) 555-0142 or a.borrower@example.com. "
    "Payment of $1,204.55 is due 03/15/2024."
)


@pytest.fixture(scope="module")
def pipeline():
    return Pipeline(TAXONOMY, build_detector("deterministic", TAXONOMY))


def test_analyze_takes_a_batch(pipeline):
    """The signature is a list from the first version.

    Throughput measured one request at a time is a latency number in costume,
    and retrofitting a batch path after the benchmark exists means re-running
    every measurement.
    """
    results = pipeline.analyze([SAMPLE, SAMPLE, "no entities here"])
    assert len(results) == 3
    assert results[0].entities and not results[2].entities


def test_result_carries_the_taxonomy_version(pipeline):
    """Drift comparisons between different label spaces are meaningless.

    Without the version recorded in the response, a taxonomy change makes the
    PSI number silently wrong rather than detectably stale.
    """
    assert pipeline.analyze([SAMPLE])[0].taxonomy_version == TAXONOMY.version


def test_result_carries_engine_identity(pipeline):
    engine = pipeline.analyze([SAMPLE])[0].engine
    assert engine["name"] == "deterministic" and engine["version"]


def test_every_result_has_a_request_id(pipeline):
    ids = {r.request_id for r in pipeline.analyze([SAMPLE] * 3)}
    assert len(ids) == 3, "batch members must be distinguishable in logs"


def test_per_stage_timings_are_recorded(pipeline):
    """"detect is 80% of p95" is only answerable if the stages are timed."""
    timing = pipeline.analyze([SAMPLE])[0].timing_ms
    assert {"detect", "arbitrate", "redact", "total"} <= set(timing)
    assert timing["total"] >= timing["detect"] > 0


def test_redaction_is_opt_in(pipeline):
    assert pipeline.analyze([SAMPLE])[0].redacted is None
    redacted = pipeline.analyze([SAMPLE], redact=True)[0].redacted
    assert redacted is not None and "457551275" not in redacted


def test_counts_are_reported_by_tier_and_type(pipeline):
    result = pipeline.analyze([SAMPLE])[0]
    assert sum(result.counts_by_tier.values()) == len(result.entities)
    assert sum(result.counts_by_type.values()) == len(result.entities)
    assert result.counts_by_tier["tier_1"] >= 2


def test_dropped_entities_are_returned_not_discarded(pipeline):
    """The rejections are the evidence that validation is doing anything."""
    text = "Reference 666121234 and routing 123456789 in the file."
    result = pipeline.analyze([text])[0]
    assert result.dropped
    assert all(e.reason for e in result.dropped)


def test_rejection_rate_is_computable(pipeline):
    """The drift signal this design makes available and label-mix PSI does not."""
    result = pipeline.analyze(["Reference 666121234 here."])[0]
    assert 0.0 <= result.rejection_rate <= 1.0


def test_losing_an_overlap_is_not_a_rejection(pipeline):
    """Was 0.333 here: overlap losers counted as validator rejections."""
    result = pipeline.analyze(["Loan number 0012345678 and account 483920117."])[0]
    assert result.dropped, "the premise needs an overlap loser"
    assert all(e.validation_status is not ValidationStatus.FAIL for e in result.dropped)
    assert result.rejection_rate == 0.0


def test_rejection_rate_ignores_readings_with_no_validator(pipeline):
    """One failed SSN, one passing PHONE; the tier-3 DATE has no validator."""
    result = pipeline.analyze(["Taxpayer SSN 666121234, call (415) 555-0142 on 03/15/2024."])[0]
    readings = [*result.entities, *result.dropped]
    assert any(e.validation_status is ValidationStatus.NOT_APPLICABLE for e in readings)
    assert result.rejection_rate == 0.5


def test_entities_never_overlap(pipeline):
    for result in pipeline.analyze([SAMPLE]):
        spans = [(e.start, e.end) for e in result.entities]
        for (_, a_end), (b_start, _) in zip(spans, spans[1:], strict=False):
            assert a_end <= b_start


def test_no_module_level_state_between_pipelines():
    """Two pipelines must not share state.

    v1 kept its model handles and compiled patterns in globals, which is what
    would stop an evaluation harness importing this and running several
    configurations in one process.
    """
    a = Pipeline(TAXONOMY, build_detector("deterministic", TAXONOMY))
    b = Pipeline(TAXONOMY, build_detector("deterministic", TAXONOMY))
    assert a.detector is not b.detector
    assert a.analyze([SAMPLE])[0].entities == b.analyze([SAMPLE])[0].entities


def test_empty_and_whitespace_input(pipeline):
    for text in ["", "   ", "\n\n"]:
        result = pipeline.analyze([text])[0]
        assert result.entities == [] and result.rejection_rate == 0.0


def test_runs_over_the_frozen_corpus(pipeline):
    """Smoke test against the committed reference set."""
    path = REPO_ROOT / "data" / "corpus" / "frozen" / "documents.jsonl"
    with path.open() as handle:
        texts = [json.loads(line)["text"] for _, line in zip(range(20), handle, strict=False)]
    results = pipeline.analyze(texts, redact=True)
    assert all(r.entities for r in results)
    assert all(r.redacted != text for r, text in zip(results, texts, strict=False))


def test_rejection_rate_is_counted_per_reading(pipeline):
    """One string, two readings: a failed SSN and a passing account number.

    Per string this would be 0.0, because the account reading survived, and
    the failed SSN reading -- the drift signal -- would vanish.
    """
    result = pipeline.analyze(["Taxpayer SSN, credit to account 666121234 today."])[0]
    assert result.rejection_rate == 0.5


def test_a_fragment_is_not_a_rejection(pipeline):
    """"0165" ends a valid phone number; it fails NMLS rules only as a piece of it."""
    result = pipeline.analyze(["Questions: Daniel Nguyen at 713-555-0165, NMLS 7108420."])[0]
    assert any(is_fragment(e) and e.validation_status is ValidationStatus.FAIL
               for e in result.dropped), "the premise needs a failing fragment"
    assert result.rejection_rate == 0.0


def test_a_passing_orphan_counts_as_a_validated_reading(pipeline):
    """A valid SSN dropped with a container that lost was still validated, and passed.

    Leaving it out of the denominator while counting its failed sibling made
    the rate 0.5 here instead of 1/3.
    """
    from app.core.arbitration import arbitrate
    from app.core.pipeline import AnalysisResult
    from app.core.types import Candidate

    document = "Lot 078-05-1120 and 666-12-1234 Rd 12-3456789"

    def at(entity_type, text):
        start = document.index(text)
        return Candidate.from_span(document=document, entity_type=entity_type, start=start,
                                   end=start + len(text), score=1.0, source="test")

    kept, dropped = arbitrate([
        at("STREET_ADDRESS", "Lot 078-05-1120 and 666-12-1234 Rd 12"),
        at("EIN", "12-3456789"),
        at("SSN", "078-05-1120"),
        at("SSN", "666-12-1234"),
    ], TAXONOMY)
    result = AnalysisResult(
        request_id="t", taxonomy_version="t", engine={}, entities=kept, dropped=dropped,
        counts_by_tier={}, counts_by_type={}, timing_ms={},
    )
    assert result.rejection_rate == 1 / 3
