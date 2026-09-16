"""Pipeline orchestration and the instrumentation the later work depends on."""

from __future__ import annotations

import json

import pytest

from app.core.pipeline import Pipeline
from app.core.taxonomy import load_taxonomy
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
