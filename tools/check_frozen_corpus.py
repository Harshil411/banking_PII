"""Assert the committed frozen corpus still regenerates from its seed.

A frozen evaluation set is only frozen if it can be rebuilt. Committing the
JSONL alone makes it an opaque blob that nobody can verify or extend; the
manifest records the seed, the taxonomy version and a SHA-256 so the set can
be reproduced and so an unintended generator change is caught rather than
quietly rebaselined.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from app.core.taxonomy import load_taxonomy
from synth.generate import generate, write_corpus
from synth.providers import PROVIDERS

FROZEN = Path("data/corpus/frozen/manifest.json")


def main() -> int:
    committed = json.loads(FROZEN.read_text(encoding="utf-8"))
    taxonomy = load_taxonomy("taxonomy/entities.yaml", known_generators=set(PROVIDERS))

    if taxonomy.version != committed["taxonomy_version"]:
        print(
            f"taxonomy version moved from {committed['taxonomy_version']} to "
            f"{taxonomy.version} without regenerating the frozen corpus.\n"
            "A drift reference built on a different label space is not a reference.",
            file=sys.stderr,
        )
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        documents = generate(
            committed["seed"], committed["n_docs"], taxonomy, committed["adversarial_rate"]
        )
        regenerated = write_corpus(
            documents,
            Path(tmp),
            committed["seed"],
            taxonomy.version,
            committed["adversarial_rate"],
        )

    if regenerated["sha256"] != committed["sha256"]:
        print(
            "the frozen corpus no longer regenerates from its seed.\n"
            f"  committed    {committed['sha256']}\n"
            f"  regenerated  {regenerated['sha256']}\n"
            "Either a generator change was unintended, or the frozen set and its "
            "manifest need regenerating together.",
            file=sys.stderr,
        )
        return 1

    print(f"frozen corpus reproduces: {committed['sha256'][:16]} ({committed['n_docs']} documents)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
