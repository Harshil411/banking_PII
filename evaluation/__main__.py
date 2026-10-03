"""Run the evaluation, write a report, and optionally gate against a baseline.

    python -m evaluation                          # score both splits, print a table
    python -m evaluation --write-baseline         # record the current numbers
    python -m evaluation --check                  # exit 1 on regression (CI)

Two splits are scored, and they answer different questions:

in_distribution
    data/corpus/frozen -- built from the templates the detection rules were
    tuned against. Answers "did a change break something that used to work".

held_out
    data/corpus/holdout -- built from templates never looked at while tuning.
    Answers "do the rules generalise past the phrasing they were fitted to".
    Report-only: changing a rule because of a held-out number makes it a second
    development set.

Everything gated is deterministic -- the pipeline has no randomness and every
tiebreak is total -- so a change in a gated number is a real change, not noise.
Latency is recorded for information and never gated: it depends on the machine.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

from app.core.arbitration import arbitrate
from app.core.taxonomy import Taxonomy, load_taxonomy
from app.detect.registry import build_detector
from evaluation.scoring import SplitScore
from synth.providers import PROVIDERS

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "evaluation" / "baseline.json"
SPLITS = {
    "in_distribution": ROOT / "data" / "corpus" / "frozen",
    "held_out": ROOT / "data" / "corpus" / "holdout",
}

#: Regression tolerances. Deliberately tight, because the numbers are
#: deterministic: these exist to let a small intentional trade-off through, not
#: to absorb noise that does not exist.
MAX_MICRO_F1_DROP = 0.005
MAX_TYPE_F1_DROP = 0.02
#: Types with less support than this are not gated individually. One document
#: can move a 10-span type by several points, and a gate that fires on that is a
#: gate people learn to ignore.
MIN_GATED_SUPPORT = 20
MAX_REJECTION_RATE_DROP = 0.01
MAX_CLAIM_RATE_RISE = 0.01


def load() -> Taxonomy:
    return load_taxonomy(ROOT / "taxonomy" / "entities.yaml", known_generators=set(PROVIDERS))


def evaluate(engine: str, taxonomy: Taxonomy | None = None) -> dict:
    taxonomy = taxonomy or load()
    detector = build_detector(engine, taxonomy)
    detector.warm()

    report: dict = {
        **_identity(engine, taxonomy),
        "commit": _commit(),
        "date": date.today().isoformat(),
        "splits": {},
    }

    for name, directory in SPLITS.items():
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        score = SplitScore()
        timings: list[float] = []
        with (directory / "documents.jsonl").open(encoding="utf-8") as handle:
            for line in handle:
                doc = json.loads(line)
                started = time.perf_counter()
                kept, _ = arbitrate(detector.detect(doc["text"]), taxonomy)
                timings.append((time.perf_counter() - started) * 1000)
                score.add_document(
                    doc["spans"],
                    [{"start": e.start, "end": e.end, "entity_type": e.entity_type} for e in kept],
                )
        report["splits"][name] = {
            "corpus": {
                "path": str(directory.relative_to(ROOT)),
                "seed": manifest["seed"],
                "sha256": manifest["sha256"],
                "templates": manifest.get("template_ids", []),
                "spans": manifest["n_spans"],
            },
            **score.summary(),
            "latency_ms": _latency(timings),
        }
    return report


def _latency(samples: list[float]) -> dict:
    ordered = sorted(samples)
    return {
        "note": "in-process, one document at a time, single thread; not an HTTP benchmark",
        "machine": f"{platform.system()} {platform.machine()}, Python {platform.python_version()}",
        "p50": round(statistics.median(ordered), 2),
        "p95": round(ordered[max(0, int(len(ordered) * 0.95) - 1)], 2),
        "max": round(ordered[-1], 2),
    }


def _commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


#: What a run must share with the baseline to be comparable at all. A different
#: engine finds different types; a different taxonomy version is a different
#: label space. Either way per-type differences are not regressions.
IDENTITY = ("engine", "taxonomy_version")


def _identity(engine: str, taxonomy: Taxonomy) -> dict:
    """The fields in IDENTITY, as a report records them. Built in one place for both uses."""
    return {"engine": engine, "taxonomy_version": taxonomy.version}


def _mismatch(baseline: dict, current: dict) -> str | None:
    """The one place the comparability rule lives; ``compare`` and ``main`` both ask it."""
    changed = [key for key in IDENTITY if baseline.get(key) != current.get(key)]
    if not changed:
        return None
    detail = ", ".join(f"{key} {baseline.get(key)} -> {current.get(key)}" for key in changed)
    return (
        f"not comparable ({detail}); per-type differences would reflect that change, not "
        "a regression. Re-run with the baseline's configuration, or regenerate the "
        "baseline deliberately"
    )


def _fail(failures: list[str]) -> int:
    print("\nthe gate failed against the committed baseline:", file=sys.stderr)
    for failure in failures:
        print(f"  - {failure}", file=sys.stderr)
    return 1


def compare(current: dict, baseline: dict) -> list[str]:
    """Return a list of regressions; empty means the gate passes."""
    # A mismatch is a comparison error, not a regression. Without this check,
    # scoring the regex-only engine against a presidio baseline reports CITY
    # and PERSON_NAME as collapsing -- the regex engine cannot find them at
    # all -- and sends someone looking for a bug that does not exist.
    mismatch = _mismatch(baseline, current)
    if mismatch:
        return [mismatch]

    failures: list[str] = []
    for split, base in baseline["splits"].items():
        now = current["splits"].get(split)
        if now is None:
            failures.append(f"{split}: split missing from current run")
            continue
        if now["corpus"]["sha256"] != base["corpus"]["sha256"]:
            failures.append(
                f"{split}: corpus changed ({base['corpus']['sha256'][:12]} -> "
                f"{now['corpus']['sha256'][:12]}); regenerate the baseline deliberately"
            )
            continue

        drop = base["strict"]["micro"]["f1"] - now["strict"]["micro"]["f1"]
        if drop > MAX_MICRO_F1_DROP:
            failures.append(
                f"{split}: micro-F1 {base['strict']['micro']['f1']:.4f} -> "
                f"{now['strict']['micro']['f1']:.4f} (drop {drop:.4f} > {MAX_MICRO_F1_DROP})"
            )

        for entity_type, base_row in base["per_type"].items():
            if base_row["support"] < MIN_GATED_SUPPORT:
                continue
            now_f1 = now["per_type"].get(entity_type, {}).get("f1", 0.0)
            if base_row["f1"] - now_f1 > MAX_TYPE_F1_DROP:
                failures.append(
                    f"{split}: {entity_type} F1 {base_row['f1']:.4f} -> {now_f1:.4f} "
                    f"(support {base_row['support']})"
                )

        rejection_drop = (
            base["adversarial"]["rejection_rate"] - now["adversarial"]["rejection_rate"]
        )
        if rejection_drop > MAX_REJECTION_RATE_DROP:
            failures.append(
                f"{split}: adversarial rejection {base['adversarial']['rejection_rate']:.4f} "
                f"-> {now['adversarial']['rejection_rate']:.4f}"
            )

        claim_rise = now["distractors"]["claim_rate"] - base["distractors"]["claim_rate"]
        if claim_rise > MAX_CLAIM_RATE_RISE:
            failures.append(
                f"{split}: distractor claim rate {base['distractors']['claim_rate']:.4f} "
                f"-> {now['distractors']['claim_rate']:.4f}"
            )
    return failures


def _print(report: dict) -> None:
    for split, body in report["splits"].items():
        strict, relaxed = body["strict"], body["relaxed"]
        print(
            f"\n{split}  ({body['documents']} documents, templates: "
            f"{', '.join(body['corpus']['templates'])})"
        )
        print(
            f"  strict  micro P {strict['micro']['precision']:.3f}"
            f"  R {strict['micro']['recall']:.3f}"
            f"  F1 {strict['micro']['f1']:.3f}   macro-F1 {strict['macro_f1']:.3f}"
        )
        print(f"  relaxed micro F1 {relaxed['micro']['f1']:.3f}")
        print(
            f"  adversarial rejected {body['adversarial']['rejection_rate']:.1%}"
            f"  (relabelled {body['adversarial']['relabelled']})"
            f"   distractors claimed {body['distractors']['claim_rate']:.1%}"
        )
        print(f"  latency p50 {body['latency_ms']['p50']} ms  p95 {body['latency_ms']['p95']} ms")
        print(f"  {'type':<16}{'P':>7}{'R':>7}{'F1':>7}{'relaxed':>9}{'n':>6}")
        for entity_type, row in body["per_type"].items():
            print(
                f"  {entity_type:<16}{row['precision']:>7.3f}{row['recall']:>7.3f}"
                f"{row['f1']:>7.3f}{row['relaxed_f1']:>9.3f}{row['support']:>6}"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score detection against the committed corpora.")
    parser.add_argument("--engine", default="presidio", choices=("presidio", "deterministic"))
    parser.add_argument("--out", type=Path, help="write the full report as JSON")
    # Exclusive: checking against a baseline this run has just overwritten
    # compares the run with itself and always passes.
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write-baseline", action="store_true", help=f"write {BASELINE.name}")
    mode.add_argument("--check", action="store_true", help="exit 1 if worse than the baseline")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    baseline = json.loads(BASELINE.read_text(encoding="utf-8")) if args.check else None
    # Without --out, a mismatch can fail before loading a model and scoring
    # both splits. With it, the report is wanted whatever the gate says, and
    # compare() reports the mismatch afterwards.
    taxonomy = load()
    if baseline is not None and not args.out:
        mismatch = _mismatch(baseline, _identity(args.engine, taxonomy))
        if mismatch:
            return _fail([mismatch])

    report = evaluate(args.engine, taxonomy)
    if not args.quiet:
        _print(report)

    if args.out:
        args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.write_baseline:
        BASELINE.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"\nbaseline written to {BASELINE.relative_to(ROOT)}")

    if baseline is not None:
        failures = compare(report, baseline)
        if failures:
            return _fail(failures)
        print(f"\nno regression against baseline {baseline['commit']} ({baseline['date']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
