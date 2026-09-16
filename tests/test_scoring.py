"""The evaluation arithmetic, against hand-built cases.

A scorer that is wrong makes every number downstream of it wrong, and it would
agree with itself on every run -- determinism does not help. So each definition
in evaluation/scoring.py gets a case small enough to check by hand.
"""

from __future__ import annotations

import pytest

from evaluation.__main__ import compare
from evaluation.scoring import Counts, SplitScore


def span(start, end, entity_type, kind="valid"):
    return {"start": start, "end": end, "entity_type": entity_type, "value_kind": kind}


def pred(start, end, entity_type):
    return {"start": start, "end": end, "entity_type": entity_type}


def test_counts_arithmetic():
    c = Counts(tp=8, fp=2, fn=4)
    assert c.precision == pytest.approx(0.8)
    assert c.recall == pytest.approx(8 / 12)
    assert c.f1 == pytest.approx(2 * 0.8 * (8 / 12) / (0.8 + 8 / 12))
    assert Counts().f1 == 0.0


def test_strict_requires_exact_offsets_and_type():
    score = SplitScore()
    score.add_document(
        [span(0, 9, "SSN"), span(20, 29, "ABA_ROUTING")],
        [pred(0, 9, "SSN"), pred(20, 28, "ABA_ROUTING")],
    )
    summary = score.summary()
    assert summary["per_type"]["SSN"]["tp"] == 1
    assert summary["per_type"]["ABA_ROUTING"] == {
        **summary["per_type"]["ABA_ROUTING"],
        "tp": 0,
        "fp": 1,
        "fn": 1,
    }


def test_relaxed_accepts_overlap_but_not_a_wrong_type():
    score = SplitScore()
    score.add_document(
        [span(0, 13, "PERSON_NAME"), span(20, 29, "SSN")],
        [pred(0, 14, "PERSON_NAME"), pred(20, 29, "US_ACCOUNT_NUM")],
    )
    summary = score.summary()
    assert summary["per_type"]["PERSON_NAME"]["f1"] == 0.0
    assert summary["per_type"]["PERSON_NAME"]["relaxed_f1"] == 1.0
    assert summary["per_type"]["SSN"]["relaxed_f1"] == 0.0


def test_relaxed_matches_each_gold_span_at_most_once():
    """Two predictions over one gold span: one true positive, one false positive."""
    score = SplitScore()
    score.add_document(
        [span(0, 20, "PERSON_NAME")], [pred(0, 5, "PERSON_NAME"), pred(8, 20, "PERSON_NAME")]
    )
    relaxed = score.relaxed["PERSON_NAME"]
    assert (relaxed.tp, relaxed.fp, relaxed.fn) == (1, 1, 0)


def test_predictions_on_non_entities_are_false_positives():
    """Adversarial and distractor spans are not entities; predicting one is wrong."""
    score = SplitScore()
    score.add_document(
        [span(0, 9, "ABA_ROUTING", "adversarial"), {**span(20, 26, None, "distractor")}],
        [pred(0, 9, "US_ACCOUNT_NUM"), pred(20, 26, "MONEY")],
    )
    summary = score.summary()
    assert summary["per_type"]["US_ACCOUNT_NUM"]["fp"] == 1
    assert summary["per_type"]["MONEY"]["fp"] == 1
    assert summary["strict"]["micro"]["tp"] == 0


def test_adversarial_rejection_and_relabelling_are_separate():
    score = SplitScore()
    score.add_document(
        [
            span(0, 9, "ABA_ROUTING", "adversarial"),  # kept as its own type: not rejected
            span(
                20, 29, "ABA_ROUTING", "adversarial"
            ),  # kept as another type: rejected, relabelled
            span(40, 49, "SSN", "adversarial"),  # kept as nothing: rejected
        ],
        [pred(0, 9, "ABA_ROUTING"), pred(20, 29, "US_ACCOUNT_NUM")],
    )
    adversarial = score.summary()["adversarial"]
    assert adversarial == {"total": 3, "rejected": 2, "relabelled": 1, "rejection_rate": 0.6667}


def test_distractor_claimed_by_any_overlap():
    score = SplitScore()
    score.add_document(
        [span(0, 6, None, "distractor"), span(10, 16, None, "distractor")],
        [pred(3, 8, "MONEY")],
    )
    assert score.summary()["distractors"] == {"total": 2, "claimed": 1, "claim_rate": 0.5}


def test_macro_f1_ignores_types_with_no_gold_support():
    score = SplitScore()
    score.add_document([span(0, 9, "SSN")], [pred(0, 9, "SSN"), pred(20, 25, "ZIP")])
    assert score.summary()["strict"]["macro_f1"] == 1.0


# --------------------------------------------------------------------------
# The regression gate
# --------------------------------------------------------------------------


def _report(micro_f1=0.97, type_f1=0.95, support=40, rejection=1.0, claim=0.02, sha="abc"):
    return {
        "splits": {
            "held_out": {
                "corpus": {"sha256": sha},
                "strict": {"micro": {"f1": micro_f1}},
                "per_type": {"LOAN_NUMBER": {"f1": type_f1, "support": support}},
                "adversarial": {"rejection_rate": rejection},
                "distractors": {"claim_rate": claim},
            }
        }
    }


def test_gate_passes_on_identical_numbers():
    assert compare(_report(), _report()) == []


def test_gate_catches_a_per_type_drop_the_aggregate_hides():
    """The reason per-type floors exist: v1's "improved" run lost 37 points on one type."""
    failures = compare(_report(micro_f1=0.969, type_f1=0.80), _report())
    assert any("LOAN_NUMBER" in f for f in failures)
    assert not any("micro-F1" in f for f in failures)


def test_gate_ignores_low_support_types():
    assert compare(_report(type_f1=0.5, support=10), _report(support=10)) == []


def test_gate_catches_micro_drop_rejection_drop_and_claim_rise():
    failures = compare(_report(micro_f1=0.95, rejection=0.9, claim=0.2), _report())
    assert any("micro-F1" in f for f in failures)
    assert any("adversarial rejection" in f for f in failures)
    assert any("distractor claim" in f for f in failures)


def test_gate_refuses_to_compare_different_corpora():
    failures = compare(_report(sha="new"), _report(sha="old"))
    assert failures and "corpus changed" in failures[0]
