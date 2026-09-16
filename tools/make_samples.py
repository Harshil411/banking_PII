"""Choose the demo page's sample documents from the committed corpora.

Samples are picked by running the real pipeline, not by template name alone. A
sample that happens to contain nothing a validator rejects makes the page open
on "0 rejected", which demonstrates nothing -- that is what the first version of
the page did. Each chosen document must show at least one tier-1 proof and at
least one candidate a validator rejected.

One held-out document is included and labelled as such, so a visitor can see
the detector on phrasing it was not tuned against.

    make samples
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.core.arbitration import arbitrate
from app.core.taxonomy import load_taxonomy
from app.detect.registry import build_detector
from synth.providers import PROVIDERS

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "app" / "web" / "static" / "assets" / "samples.json"
MAX_CHARS = 1400

WANTED = [
    ("in_distribution", "data/corpus/frozen", "payoff_demand", "Payoff demand"),
    ("in_distribution", "data/corpus/frozen", "call_center_note", "Call note"),
    ("in_distribution", "data/corpus/frozen", "notice_of_error_response", "RESPA error response"),
    ("in_distribution", "data/corpus/frozen", "collection_call_log", "Collection log"),
    ("held_out", "data/corpus/holdout", "escrow_email_thread", "Escrow email"),
]


def showcases_the_thesis(doc: dict, detector, taxonomy) -> bool:
    kept, dropped = arbitrate(detector.detect(doc["text"]), taxonomy)
    proves = any(int(e.tier) == 1 for e in kept)
    rejects = any(
        d.validation_status.value == "fail" and not any(k.overlaps(d) for k in kept)
        for d in dropped
    )
    return proves and rejects


def main() -> int:
    taxonomy = load_taxonomy(ROOT / "taxonomy" / "entities.yaml", known_generators=set(PROVIDERS))
    detector = build_detector("presidio", taxonomy)
    detector.warm()

    samples = []
    for split, corpus, template, label in WANTED:
        chosen = None
        with (ROOT / corpus / "documents.jsonl").open(encoding="utf-8") as handle:
            for line in handle:
                doc = json.loads(line)
                if doc["template_id"] != template or len(doc["text"]) > MAX_CHARS:
                    continue
                if showcases_the_thesis(doc, detector, taxonomy):
                    chosen = doc
                    break
        if chosen is None:
            print(f"no {template} document shows both a proof and a rejection", file=sys.stderr)
            return 1
        samples.append(
            {"label": label, "split": split, "doc_id": chosen["doc_id"], "text": chosen["text"]}
        )
        print(f"  {label:<22} {chosen['doc_id']}  {len(chosen['text'])} chars")

    OUTPUT.write_text(json.dumps(samples, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(samples)} samples to {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
