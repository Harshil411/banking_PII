"""Scoring probe used during development to settle design calls on data.

Not the evaluation harness -- that lands with the CI gate, and will share this
scoring logic. This exists so questions like "should SSN be context-gated" are
answered by measurement rather than by argument. Several were:

    ungated SSN                      precision 0.164, ABA recall 0.022
    + context gating                 precision 0.236
    + word-boundary context match    precision 0.382, ABA recall 0.543
    + window 32, formatted PHONE,    micro-F1 0.948
      gated ABA and US_ACCOUNT_NUM

Usage::

    PYTHONPATH=. .venv/bin/python tools/probe_eval.py [corpus] [limit] [engine]
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict

from app.core.arbitration import arbitrate
from app.core.taxonomy import load_taxonomy
from app.detect.registry import build_detector
from synth.providers import PROVIDERS


def main() -> int:
    corpus = sys.argv[1] if len(sys.argv) > 1 else "data/corpus/dev/documents.jsonl"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 150
    engine = sys.argv[3] if len(sys.argv) > 3 else "deterministic"

    taxonomy = load_taxonomy("taxonomy/entities.yaml", known_generators=set(PROVIDERS))
    detector = build_detector(engine, taxonomy)
    detector.warm()

    tp: dict[str, int] = defaultdict(int)
    fp: dict[str, int] = defaultdict(int)
    fn: dict[str, int] = defaultdict(int)
    adversarial_total = adversarial_rejected = 0
    distractor_total = distractor_claimed = 0
    documents = 0

    with open(corpus) as handle:
        for line_no, line in enumerate(handle):
            if line_no >= limit:
                break
            documents += 1
            doc = json.loads(line)
            kept, _ = arbitrate(detector.detect(doc["text"]), taxonomy)
            predicted = {(e.start, e.end): e.entity_type for e in kept}

            gold = {
                (s["start"], s["end"]): s["entity_type"]
                for s in doc["spans"]
                if s["value_kind"] == "valid"
            }
            for span, label in gold.items():
                if predicted.get(span) == label:
                    tp[label] += 1
                else:
                    fn[label] += 1
            for span, label in predicted.items():
                if gold.get(span) != label:
                    fp[label] += 1

            for span_record in doc["spans"]:
                span = (span_record["start"], span_record["end"])
                if span_record["value_kind"] == "adversarial":
                    adversarial_total += 1
                    adversarial_rejected += span not in predicted
                elif span_record["value_kind"] == "distractor":
                    distractor_total += 1
                    distractor_claimed += any(
                        p[0] < span[1] and span[0] < p[1] for p in predicted
                    )

    _report(engine, documents, tp, fp, fn)
    _rate("adversarial spans", adversarial_total, "kept out of entities", adversarial_rejected)
    _rate("distractor spans", distractor_total, "claimed by a detection", distractor_claimed)
    return 0


def _f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _report(engine: str, documents: int, tp, fp, fn) -> None:
    print(f"engine={engine}  docs={documents}\n")
    print(f"{'type':<17}{'TP':>6}{'FP':>6}{'FN':>6}{'prec':>8}{'rec':>8}{'F1':>8}")
    totals = [0, 0, 0]
    for label in sorted(set(tp) | set(fp) | set(fn)):
        hit, miss, missed = tp[label], fp[label], fn[label]
        precision = hit / (hit + miss) if hit + miss else 0.0
        recall = hit / (hit + missed) if hit + missed else 0.0
        totals[0] += hit
        totals[1] += miss
        totals[2] += missed
        print(
            f"{label:<17}{hit:>6}{miss:>6}{missed:>6}"
            f"{precision:>8.3f}{recall:>8.3f}{_f1(precision, recall):>8.3f}"
        )
    hit, miss, missed = totals
    precision = hit / (hit + miss) if hit + miss else 0.0
    recall = hit / (hit + missed) if hit + missed else 0.0
    print(
        f"\n{'MICRO':<17}{hit:>6}{miss:>6}{missed:>6}"
        f"{precision:>8.3f}{recall:>8.3f}{_f1(precision, recall):>8.3f}"
    )


def _rate(total_label: str, total: int, part_label: str, part: int) -> None:
    share = part / total if total else 0.0
    print(f"\n{total_label:<25}{total}")
    print(f"  {part_label:<23}{part}  ({share:.1%})")


if __name__ == "__main__":
    sys.exit(main())
