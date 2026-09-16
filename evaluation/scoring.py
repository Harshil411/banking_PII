"""Scoring predicted entities against synthetic gold spans.

Pure functions over plain dicts, so the arithmetic can be unit-tested against
hand-built cases without running a detector.

Definitions, stated because every one of them is a choice someone can
reasonably challenge:

strict match
    Same entity type and identical character offsets. The headline metric.

relaxed match
    Same entity type and any character overlap, each gold span matched at most
    once. Reported alongside strict because boundary disagreements ("Maria
    Delgado" versus "Maria Delgado,") are a different failure from missing an
    entity entirely, and a single number hides which one is happening.

true positives are counted only against VALID gold spans
    Adversarial and distractor spans are not entities. A prediction that lands
    on one counts as a false positive for whatever type was predicted. That is
    conservative: an adversarial routing number relabelled as an account number
    is arguably a reasonable reading, and it is still scored as wrong.

adversarial rejection
    An adversarial span is rejected when no kept entity of its own type
    overlaps it. This is the claim the validators exist to support -- "the
    checksum proved this is not a routing number" -- and it is kept separate
    from whether the span survived under a different label, which is reported
    as relabelled.

distractor claim
    A distractor is claimed when any kept entity overlaps it.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field


@dataclass
class Counts:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    @property
    def support(self) -> int:
        return self.tp + self.fn

    def as_dict(self) -> dict:
        return {
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "support": self.support,
        }


@dataclass
class SplitScore:
    strict: dict[str, Counts] = field(default_factory=lambda: defaultdict(Counts))
    relaxed: dict[str, Counts] = field(default_factory=lambda: defaultdict(Counts))
    adversarial_total: int = 0
    adversarial_rejected: int = 0
    adversarial_relabelled: int = 0
    distractor_total: int = 0
    distractor_claimed: int = 0
    documents: int = 0

    def add_document(self, gold_spans: Iterable[dict], predicted: Iterable[dict]) -> None:
        gold = list(gold_spans)
        pred = list(predicted)
        self.documents += 1

        valid = [g for g in gold if g["value_kind"] == "valid"]
        _score_strict(self.strict, valid, pred)
        _score_relaxed(self.relaxed, valid, pred)

        for span in gold:
            overlapping = [p for p in pred if _overlaps(p, span)]
            if span["value_kind"] == "adversarial":
                self.adversarial_total += 1
                same_type = any(p["entity_type"] == span["entity_type"] for p in overlapping)
                if not same_type:
                    self.adversarial_rejected += 1
                    if overlapping:
                        self.adversarial_relabelled += 1
            elif span["value_kind"] == "distractor":
                self.distractor_total += 1
                if overlapping:
                    self.distractor_claimed += 1

    def summary(self) -> dict:
        strict_micro = _micro(self.strict.values())
        relaxed_micro = _micro(self.relaxed.values())
        types = sorted(set(self.strict) | set(self.relaxed))
        supported = [t for t in types if self.strict[t].support]
        return {
            "documents": self.documents,
            "strict": {
                "micro": strict_micro.as_dict(),
                "macro_f1": round(
                    sum(self.strict[t].f1 for t in supported) / len(supported), 4
                )
                if supported
                else 0.0,
            },
            "relaxed": {"micro": relaxed_micro.as_dict()},
            "per_type": {
                t: {
                    **self.strict[t].as_dict(),
                    "relaxed_f1": round(self.relaxed[t].f1, 4),
                }
                for t in types
            },
            "adversarial": {
                "total": self.adversarial_total,
                "rejected": self.adversarial_rejected,
                "relabelled": self.adversarial_relabelled,
                "rejection_rate": _rate(self.adversarial_rejected, self.adversarial_total),
            },
            "distractors": {
                "total": self.distractor_total,
                "claimed": self.distractor_claimed,
                "claim_rate": _rate(self.distractor_claimed, self.distractor_total),
            },
        }


def _overlaps(a: dict, b: dict) -> bool:
    return a["start"] < b["end"] and b["start"] < a["end"]


def _rate(part: int, total: int) -> float:
    return round(part / total, 4) if total else 0.0


def _micro(counts: Iterable[Counts]) -> Counts:
    total = Counts()
    for c in counts:
        total.tp += c.tp
        total.fp += c.fp
        total.fn += c.fn
    return total


def _score_strict(table: dict[str, Counts], gold: list[dict], pred: list[dict]) -> None:
    gold_keys = {(g["start"], g["end"], g["entity_type"]) for g in gold}
    pred_keys = {(p["start"], p["end"], p["entity_type"]) for p in pred}
    for key in gold_keys:
        if key in pred_keys:
            table[key[2]].tp += 1
        else:
            table[key[2]].fn += 1
    for key in pred_keys - gold_keys:
        table[key[2]].fp += 1


def _score_relaxed(table: dict[str, Counts], gold: list[dict], pred: list[dict]) -> None:
    """Greedy one-to-one matching on type plus overlap, in document order."""
    unmatched_pred = sorted(pred, key=lambda p: (p["start"], p["end"]))
    for g in sorted(gold, key=lambda g: (g["start"], g["end"])):
        match = next(
            (
                p
                for p in unmatched_pred
                if p["entity_type"] == g["entity_type"] and _overlaps(p, g)
            ),
            None,
        )
        if match is None:
            table[g["entity_type"]].fn += 1
        else:
            table[g["entity_type"]].tp += 1
            unmatched_pred.remove(match)
    for p in unmatched_pred:
        table[p["entity_type"]].fp += 1
