"""Deterministic synthetic corpus generator.

Run as::

    python -m synth.generate --seed 42 --n 500 --out data/corpus/dev

Writes ``documents.jsonl`` and ``manifest.json``. The manifest carries the
seed, taxonomy version, generator version, document count and a SHA-256 of the
JSONL, so a frozen evaluation set is reproducible *from the manifest* rather
than trusted as an opaque committed blob.

THE RULE THAT MATTERS: gold spans are recorded as the document is built, never
recovered afterwards by searching the finished text. Rendering a template and
then calling ``str.find`` to locate each value is the trap, and it fails
quietly -- a borrower's name appears in the letterhead and again in the body,
``find`` returns the first, and the evaluation set becomes subtly wrong in a
way that reads as a model-quality problem for a week. Here the offsets are a
byproduct of construction and cannot disagree with the text.

Three kinds of value are placed:

``valid``        a well-formed instance of the type
``adversarial``  passes the type's pattern, fails its validator
``distractor``   servicing text that is PII-shaped but is not PII at all
                 (interest rates, form numbers, CFR citations, batch ids)

The distractors are the ones most easily forgotten and they are what make the
precision number mean anything. Without them, the cheapest way to score well
on synthetic data is to claim every digit run on the page.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from random import Random

from app.core.taxonomy import Taxonomy, load_taxonomy
from app.core.types import GoldSpan, ValueKind
from synth.providers import PROVIDERS, distractor, email_for, state_abbreviation

GENERATOR_VERSION = "1.0.0"

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = Path(__file__).parent / "templates"
#: Templates never used while tuning detection rules. Corpora generated from
#: these are report-only: adjusting a rule because of a held-out number turns
#: the held-out set into a second development set and the number into fiction.
HOLDOUT_TEMPLATE_DIR = Path(__file__).parent / "templates_holdout"
DEFAULT_TAXONOMY = REPO_ROOT / "taxonomy" / "entities.yaml"

_TOKEN = re.compile(
    r"\{\{SLOT:(?P<type>[A-Z_]+):(?P<name>[a-z0-9_]+)(?:\|(?P<form>[a-z]+))?\}\}"
    r"|\{\{DISTRACTOR(?::(?P<distractor>[a-z]+))?\}\}"
)


@dataclass(frozen=True, slots=True)
class Slot:
    entity_type: str
    name: str
    form: str | None


@dataclass(frozen=True, slots=True)
class Distractor:
    """Marker for a distractor position, optionally constrained to a category."""

    category: str | None = None

Part = str | Slot | Distractor


@dataclass(frozen=True, slots=True)
class Template:
    name: str
    parts: tuple[Part, ...]


def parse_template(name: str, body: str) -> Template:
    parts: list[Part] = []
    cursor = 0
    for match in _TOKEN.finditer(body):
        if match.start() > cursor:
            parts.append(body[cursor : match.start()])
        if match.group(0).startswith("{{DISTRACTOR"):
            parts.append(Distractor(match.group("distractor")))
        else:
            parts.append(Slot(match.group("type"), match.group("name"), match.group("form")))
        cursor = match.end()
    if cursor < len(body):
        parts.append(body[cursor:])
    return Template(name=name, parts=tuple(parts))


def load_templates(directory: Path = TEMPLATE_DIR) -> list[Template]:
    paths = sorted(directory.glob("*.txt"))
    if not paths:
        raise FileNotFoundError(f"no templates found in {directory}")
    return [parse_template(p.stem, p.read_text(encoding="utf-8")) for p in paths]


def _resolve(
    slot: Slot,
    taxonomy: Taxonomy,
    rng: Random,
    adversarial_rate: float,
    borrower_name: str | None,
) -> tuple[str, ValueKind, str]:
    """Produce one value for ``slot``, choosing valid or adversarial."""
    spec = taxonomy[slot.entity_type]
    provider = PROVIDERS[spec.generator]

    if slot.form == "abbrev" and slot.entity_type == "US_STATE":
        return state_abbreviation(rng), ValueKind.VALID, ""

    if slot.entity_type == "EMAIL" and borrower_name and rng.random() < 0.7:
        return email_for(rng, borrower_name), ValueKind.VALID, ""

    if provider.has_adversarial and rng.random() < adversarial_rate:
        generated = provider.make(rng, ValueKind.ADVERSARIAL)
        return generated.text, generated.kind, generated.note

    generated = provider.make(rng, ValueKind.VALID)
    return generated.text, generated.kind, generated.note


def render(
    template: Template,
    taxonomy: Taxonomy,
    rng: Random,
    adversarial_rate: float,
) -> tuple[str, list[GoldSpan]]:
    """Build one document, recording every span's offsets as it is assembled."""
    # Resolve a borrower name first so email addresses can be derived from it
    # and the document reads coherently.
    borrower_name: str | None = None
    for part in template.parts:
        if isinstance(part, Slot) and part.entity_type == "PERSON_NAME" and "borrower" in part.name:
            borrower_name = PROVIDERS["person_name"].valid(rng)
            break

    resolved: dict[str, tuple[str, ValueKind, str]] = {}
    pieces: list[str] = []
    spans: list[GoldSpan] = []
    cursor = 0

    for part in template.parts:
        if isinstance(part, str):
            pieces.append(part)
            cursor += len(part)
            continue

        if isinstance(part, Distractor):
            text, note = distractor(rng, part.category)
            spans.append(
                GoldSpan(
                    entity_type=None,
                    start=cursor,
                    end=cursor + len(text),
                    text=text,
                    tier=None,
                    value_kind=ValueKind.DISTRACTOR,
                    note=note,
                )
            )
            pieces.append(text)
            cursor += len(text)
            continue

        key = f"{part.entity_type}:{part.name}:{part.form or ''}"
        if key not in resolved:
            if (
                part.entity_type == "PERSON_NAME"
                and "borrower" in part.name
                and borrower_name is not None
            ):
                resolved[key] = (borrower_name, ValueKind.VALID, "")
            else:
                resolved[key] = _resolve(part, taxonomy, rng, adversarial_rate, borrower_name)
        text, kind, note = resolved[key]

        spans.append(
            GoldSpan(
                entity_type=part.entity_type,
                start=cursor,
                end=cursor + len(text),
                text=text,
                tier=int(taxonomy.tier_of(part.entity_type)),
                value_kind=kind,
                note=note,
            )
        )
        pieces.append(text)
        cursor += len(text)

    return "".join(pieces), spans


def generate(
    seed: int,
    count: int,
    taxonomy: Taxonomy,
    adversarial_rate: float = 0.15,
    templates: list[Template] | None = None,
) -> list[dict]:
    templates = templates or load_templates()
    rng = Random(seed)
    documents = []
    for index in range(count):
        template = templates[index % len(templates)]
        text, spans = render(template, taxonomy, rng, adversarial_rate)
        documents.append(
            {
                "doc_id": f"{seed}-{index:06d}",
                "template_id": template.name,
                "text": text,
                "spans": [s.as_dict() for s in spans],
            }
        )
    return documents


def write_corpus(
    documents: list[dict],
    out_dir: Path,
    seed: int,
    taxonomy_version: str,
    adversarial_rate: float,
    template_dir: Path = TEMPLATE_DIR,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / "documents.jsonl"

    payload = "".join(
        json.dumps(doc, ensure_ascii=False, sort_keys=True) + "\n" for doc in documents
    ).encode("utf-8")
    jsonl_path.write_bytes(payload)

    kinds: dict[str, int] = {}
    types: dict[str, int] = {}
    for doc in documents:
        for span in doc["spans"]:
            kinds[span["value_kind"]] = kinds.get(span["value_kind"], 0) + 1
            label = span["entity_type"] or "(distractor)"
            types[label] = types.get(label, 0) + 1

    manifest = {
        "seed": seed,
        "taxonomy_version": taxonomy_version,
        "generator_version": GENERATOR_VERSION,
        "adversarial_rate": adversarial_rate,
        "template_dir": template_dir.name,
        "template_ids": sorted({doc["template_id"] for doc in documents}),
        "n_docs": len(documents),
        "n_spans": sum(len(d["spans"]) for d in documents),
        "spans_by_kind": dict(sorted(kinds.items())),
        "spans_by_type": dict(sorted(types.items())),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n", type=int, default=500, dest="count")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "data" / "corpus" / "dev")
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY)
    parser.add_argument("--adversarial-rate", type=float, default=0.15)
    parser.add_argument(
        "--templates",
        choices=("tuning", "holdout"),
        default="tuning",
        help="tuning: templates used while developing the rules; holdout: never used for tuning",
    )
    args = parser.parse_args(argv)

    template_dir = HOLDOUT_TEMPLATE_DIR if args.templates == "holdout" else TEMPLATE_DIR
    taxonomy = load_taxonomy(args.taxonomy, known_generators=set(PROVIDERS))
    documents = generate(
        args.seed, args.count, taxonomy, args.adversarial_rate, load_templates(template_dir)
    )
    manifest = write_corpus(
        documents, args.out, args.seed, taxonomy.version, args.adversarial_rate, template_dir
    )

    print(f"wrote {manifest['n_docs']} documents, {manifest['n_spans']} spans -> {args.out}")
    print(f"  sha256 {manifest['sha256']}")
    print(f"  by kind {manifest['spans_by_kind']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
