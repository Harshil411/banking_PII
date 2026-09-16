# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Working agreement

Harshil originally wrote all code here himself, with Claude restricted to review
and scaffolding. **That was lifted on 2026-09-15**: Claude writes the
implementation and `DECISIONS.md`. The goal it served has not changed — the
project exists to be interrogated in interviews — so it is served instead by a
walkthrough session covering the whole system after the build.

`DECISIONS.md` carries one dated paragraph per real choice, each stating what
was rejected and why. Keep writing entries there for decisions of that weight;
it is read by someone deciding whether the author understood their own project.

## What this is

PII detection and redaction for US mortgage and loan-servicing text. Rebuilt
2026-09-15 from a v1 that targeted Indian banking entities — see the top two
entries in `DECISIONS.md` for why nothing from it survived.

The claim the project is built to support: detection stacks usually arbitrate
overlapping spans by model confidence; this one arbitrates by **evidence
class**. Anything that weakens the visibility of *why* a span was kept or
rejected weakens the whole thing.

## Commands

```bash
source .venv/bin/activate                       # Python 3.14 locally, 3.12 in the image
pytest -p no:warnings                           # 176 tests, ~3s
pytest -m "not slow"                            # skips tests needing the spaCy model
ruff check app synth tests tools
uvicorn app.main:app --port 8000                # demo at /

python -m synth.generate --seed 42 --n 500 --out data/corpus/dev
PYTHONPATH=. python tools/check_frozen_corpus.py    # frozen set still reproduces?
PYTHONPATH=. python tools/probe_eval.py data/corpus/frozen/documents.jsonl 120 presidio
PYTHONPATH=. python tools/make_samples.py           # after regenerating the frozen corpus
```

`tools/` scripts need `PYTHONPATH=.`; they are not part of the package.

## Architecture

```
detect ──▶ validate ──▶ arbitrate ──▶ entities[] + dropped[] ──▶ anonymize
```

`taxonomy/entities.yaml` is the single source of truth for four consumers:
runtime validation, the synthetic generator, the evaluation label set, and the
drift bin space. Changing it changes all four. Bump `version` when the label
space moves — drift comparisons across different label spaces are meaningless,
and the version is echoed in every response so a mismatch is detectable.

**Tier means strength of evidence, not kind of detector.** A tier-3 entity may
come from a regex; a tier-2 entity may come from a model. Tier-1 rules are not
equally strong either — Luhn excludes ~90% of digit strings, the SSA rules only
~25%, which is why `SSN` is context-gated despite being tier 1.

### Load-bearing invariants

- **`Candidate.from_span` is the only supported constructor for detector output.**
  Text is always sliced from the source document. v1 trusted the tokenizer's own
  surface string and inherited `##` subword artifacts.
- **Scanners are permissive; validators are strict.** A scanner that encodes its
  own correctness rules makes them unreachable — an earlier `MONEY` pattern
  encoded thousands grouping, so malformed amounts were never matched whole and
  the validator's grouping rule never fired.
- **Patterns are authored in scanner form only.** The anchored validator form is
  derived at load time; authoring both is how they drift apart.
- **Arbitration output is pairwise non-overlapping and sorted.** `anonymize`
  depends on it and raises if violated.
- **Every tiebreak must be deterministic.** A frozen evaluation set whose diffs
  shuffle is not a regression gate.
- **No module-level mutable state.** The eval harness must import the pipeline
  and run several configurations in one process.
- **Presidio is candidate generation only.** Its registry is trimmed to the spaCy
  recognizer. Re-enabling its stock recognizers would corrupt precision in a way
  that looks like a model regression; `test_detect.py` asserts against it.

### Before changing arbitration precedence

Three orderings were measured (`DECISIONS.md`, "Arbitration precedence"). Tier
first won each time. Measure before changing it:

```bash
PYTHONPATH=. python tools/probe_eval.py data/corpus/dev/documents.jsonl 300 presidio
```

Current standing on the frozen corpus: micro-F1 0.977, 94.4% of adversarial
near-misses rejected, 2.7% of distractors claimed.

### The generator

Gold spans are recorded **as documents are assembled**, never recovered by
searching the finished text. Check digits are constructed forward and `synth/`
never calls a validator — generator and validator must be able to disagree, or a
misread specification hides in both.

Regenerating the frozen corpus changes its sha256 and CI will fail until the
manifest is committed with it. Run `tools/make_samples.py` afterwards so the
demo samples stay consistent with their stated provenance.

### Testing

`tests/test_taxonomy_contract.py` is the highest-value file: it catches both v1
defects (a pattern that matches nothing fails its own examples; two types with
identical patterns). `tests/fixtures/external_vectors.json` holds
externally-sourced validator vectors, deliberately not generated by this project.

Arbitration is property-tested with hypothesis — non-overlapping, sorted,
idempotent, order-independent. Order-independence is the one that catches real
bugs.

## Not yet built

Throughput, p95 latency, cost per 1,000 documents, and PSI drift are all
unmeasured; the service is instrumented for them but no number is claimed. The
CI regression gate is stubbed and disabled pending `baseline.json`. Docker has
never been built on this machine — the Dockerfile and its CI job are unverified
locally.
