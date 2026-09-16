"""Assert every committed corpus still regenerates byte-for-byte from its manifest.

A frozen evaluation set is only frozen if it can be rebuilt. Committing the
JSONL alone makes it an opaque blob nobody can verify; the manifest records the
seed, template set, taxonomy version and a SHA-256, so an unintended generator
or template change is caught here rather than quietly absorbed into a new
baseline.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from app.core.taxonomy import load_taxonomy
from synth.generate import (
    HOLDOUT_TEMPLATE_DIR,
    TEMPLATE_DIR,
    generate,
    load_templates,
    write_corpus,
)
from synth.providers import PROVIDERS

ROOT = Path(__file__).resolve().parents[1]
CORPORA = ("data/corpus/frozen", "data/corpus/holdout")
TEMPLATE_DIRS = {TEMPLATE_DIR.name: TEMPLATE_DIR, HOLDOUT_TEMPLATE_DIR.name: HOLDOUT_TEMPLATE_DIR}


def check(corpus: Path, taxonomy) -> str | None:
    committed = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))
    if taxonomy.version != committed["taxonomy_version"]:
        return (
            f"{corpus}: taxonomy moved {committed['taxonomy_version']} -> {taxonomy.version} "
            "without regenerating this corpus"
        )
    template_dir = TEMPLATE_DIRS[committed["template_dir"]]
    with tempfile.TemporaryDirectory() as tmp:
        regenerated = write_corpus(
            generate(
                committed["seed"],
                committed["n_docs"],
                taxonomy,
                committed["adversarial_rate"],
                load_templates(template_dir),
            ),
            Path(tmp),
            committed["seed"],
            taxonomy.version,
            committed["adversarial_rate"],
            template_dir,
        )
    if regenerated["sha256"] != committed["sha256"]:
        return (
            f"{corpus}: no longer regenerates from its seed\n"
            f"    committed    {committed['sha256']}\n"
            f"    regenerated  {regenerated['sha256']}\n"
            "  Either a generator or template change was unintended, or the corpus, its "
            "manifest and evaluation/baseline.json need regenerating together."
        )
    return None


def main() -> int:
    taxonomy = load_taxonomy(ROOT / "taxonomy" / "entities.yaml", known_generators=set(PROVIDERS))
    failures = []
    for relative in CORPORA:
        problem = check(ROOT / relative, taxonomy)
        if problem:
            failures.append(problem)
        else:
            sha = json.loads((ROOT / relative / "manifest.json").read_text())["sha256"]
            print(f"{relative} reproduces ({sha[:16]})")
    for failure in failures:
        print(failure, file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
