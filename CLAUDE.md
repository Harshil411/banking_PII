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
make install          # .venv (Python 3.14 locally, 3.12 in the image), deps, spaCy model
make test             # 212 tests, ~3s; `pytest -m "not slow"` skips spaCy-dependent ones
make lint             # ruff over app synth evaluation tests tools
make serve            # API + demo at http://localhost:8000
make eval             # score both splits
make eval-check       # the CI gate: exit 1 on regression against evaluation/baseline.json
make corpus           # regenerate data/corpus/{frozen,holdout}
make check-corpora    # both corpora still regenerate byte-for-byte?
make baseline         # rewrite evaluation/baseline.json -- deliberate, commit it on its own
make samples          # re-pick demo samples (runs the pipeline)
make screenshots      # README images; needs playwright, see tools/screenshots.py
```

Single test: `.venv/bin/python -m pytest tests/test_arbitration.py::test_arbitration_is_order_independent`.
`tools/` scripts need `PYTHONPATH=.`; the Makefile sets it.

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

### Evaluation: two splits, and a rule about the second

`data/corpus/frozen` is built from `synth/templates/` — the templates every rule
was tuned against. `data/corpus/holdout` is built from `synth/templates_holdout/`,
never used while tuning. **Never change a rule because of a held-out number**;
that turns it into a second dev set. Tune against a fresh dev corpus
(`python -m synth.generate --seed 42 --n 500 --out data/corpus/dev`) and let the
held-out split report.

Strict micro-F1 is 0.977 on both. Do not cite near-miss rejection (100%) as a
result: the generator only emits values a test proves the validator rejects, so
it is true by construction. The informative numbers are distractor claim rate
and near-misses relabelled (`DECISIONS.md`, 2026-09-16).

Three arbitration orderings were measured and tier-first won. Measure with
`make eval` before changing precedence.

Changing templates, providers or the taxonomy changes corpus hashes: run
`make corpus`, `make check-corpora`, commit, then `make baseline` and commit that
separately so the baseline's `commit` field names the code that produced it.
Then `make samples`.

### The generator

Gold spans are recorded **as documents are assembled**, never recovered by
searching the finished text. Check digits are constructed forward and `synth/`
never calls a validator — generator and validator must be able to disagree, or a
misread specification hides in both.

The eval gate refuses to compare a corpus whose sha256 changed; see above for
the regeneration order.

### Testing

`tests/test_taxonomy_contract.py` is the highest-value file: it catches both v1
defects (a pattern that matches nothing fails its own examples; two types with
identical patterns). `tests/fixtures/external_vectors.json` holds
externally-sourced validator vectors, deliberately not generated by this project.

There is no JavaScript runtime in the toolchain, so the demo page's offset walk
(`segments()` in `app/web/static/assets/app.js`) is checked by a transliteration
in `test_demo_page.py`. A deliberate duplicate that can drift; keep them in step.

### The demo page

`app/web/static/` — no build step. It runs under a strict CSP with no
`unsafe-inline`: **no inline `<script>`, no `style=""` attributes, no
`innerHTML`** (it renders pasted text). Set dynamic styles through the CSSOM.
No third-party requests; fonts are self-hosted with their OFL licences. Tier
must never be conveyed by colour alone. After UI changes, re-run
`make screenshots` and check with a browser — tests cannot see layout.

Arbitration is property-tested with hypothesis — non-overlapping, sorted,
idempotent, order-independent. Order-independence is the one that catches real
bugs.

## Not yet built

HTTP throughput under concurrency, cost per 1,000 documents, and PSI drift are
unmeasured; the report's latency is in-process only. Docker has never been built
on this machine — the Dockerfile and its CI job are unverified locally. The
demo has passed axe-core (WCAG 2.2 AA) and a keyboard check, not a screen-reader
pass.
