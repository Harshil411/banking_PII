# Mortgage PII Service

PII detection and redaction for US mortgage and loan-servicing text. Every span
is checked against a validator, and **how strong that check is** is recorded as
a tier. Rejected candidates come back with the arithmetic that rejected them
rather than being quietly dropped.

The distinction that matters: most detection stacks arbitrate overlapping spans
by model confidence. This one arbitrates by **evidence class** — a mod-10 proof
outranks a 0.99 softmax, because one is arithmetic and the other is an opinion.

---

## Results

Measured on `data/corpus/frozen` — 120 synthetic servicing documents, 2,376
labelled spans, reproducible from seed `20260915` and its manifest.

| | |
|---|---|
| **Micro-F1** | **0.977** |
| Precision | 0.981 |
| Recall | 0.972 |
| Types at F1 ≥ 0.99 | 13 of 19 |
| **Adversarial near-misses rejected** | **94.4%** |
| Distractors claimed by any detection | 2.7% |

The last two rows are the ones worth reading. The corpus deliberately contains
values that *pass a type's regex and fail its validator* — a routing number one
digit off its checksum, an SSN in the 900-range — and separately contains
servicing text that is PII-shaped but is not PII: interest rates, CFR
citations, form numbers, imaging-system document ids. A precision figure
measured without those is close to meaningless, because the cheapest way to
score well on synthetic data is to claim every digit run on the page.

<details>
<summary>Per-type results</summary>

| Type | Tier | P | R | F1 |
|---|---|---|---|---|
| ABA_ROUTING | 1 | 1.000 | 1.000 | 1.000 |
| CREDIT_CARD | 1 | 1.000 | 1.000 | 1.000 |
| MERS_MIN | 1 | 1.000 | 1.000 | 1.000 |
| SSN | 1 | 0.909 | 1.000 | 0.952 |
| DATE | 3 | 1.000 | 1.000 | 1.000 |
| EIN | 2 | 1.000 | 1.000 | 1.000 |
| EMAIL | 2 | 1.000 | 1.000 | 1.000 |
| ITIN | 2 | 1.000 | 1.000 | 1.000 |
| MONEY | 2 | 1.000 | 1.000 | 1.000 |
| PHONE | 2 | 1.000 | 1.000 | 1.000 |
| STREET_ADDRESS | 3 | 1.000 | 1.000 | 1.000 |
| US_STATE | 2 | 1.000 | 1.000 | 1.000 |
| ZIP | 2 | 0.990 | 1.000 | 0.995 |
| PERSON_NAME | 3 | 0.951 | 0.967 | 0.959 |
| NMLS_ID | 2 | 0.881 | 1.000 | 0.937 |
| LOAN_NUMBER | 2 | 0.970 | 0.898 | 0.933 |
| CITY | 3 | 0.955 | 0.803 | 0.872 |
| US_ACCOUNT_NUM | 2 | 0.824 | 0.737 | 0.778 |
| CREDIT_SCORE | 3 | 1.000 | 1.000 | 1.000 |

Reproduce with `PYTHONPATH=. python tools/probe_eval.py data/corpus/frozen/documents.jsonl 120 presidio`.

</details>

---

## The tiers

Tier means **strength of evidence that a span is a true instance of the type**.
It does not mean what kind of detector produced it — a tier-3 entity may come
from a regex, and a tier-2 entity may come from a model.

| Tier | Meaning | Types |
|---|---|---|
| **1** — arithmetic | A checksum or issuing rule can prove the value impossible | `SSN` `ABA_ROUTING` `CREDIT_CARD` `MERS_MIN` |
| **2** — structural | A deterministic rule rejects values the pattern accepts | `EIN` `ITIN` `PHONE` `EMAIL` `ZIP` `US_ACCOUNT_NUM` `LOAN_NUMBER` `NMLS_ID` `US_STATE` `MONEY` |
| **3** — contextual | No rule can confirm it; the evidence is the surrounding text | `PERSON_NAME` `STREET_ADDRESS` `CITY` `DATE` `CREDIT_SCORE` |

Tier-1 rules are not equally strong, and the taxonomy says so. Luhn rejects
about 90% of digit strings; the SSA's rules reject about a quarter. That is why
`SSN` is context-gated despite being tier 1 — ungated it claimed every routing
and account number on the page, at precision 0.164.

---

## How it works

```
document
   │
   ├─ deterministic scanners          taxonomy regexes, context-gated where the
   │                                  pattern alone is too broad
   ├─ spaCy NER via Presidio          PERSON and LOCATION only
   │
   ▼
candidates ──▶ validate ──▶ arbitrate ──▶ entities[]  +  dropped[] with reasons
                                  │
                                  └─▶ anonymize (back-to-front, overlap-guarded)
```

Arbitration precedence: tier, then span length, then context-word proximity,
then score, then declaration order. The chain is total, because a frozen
evaluation set whose diffs shuffle is not a regression gate.

**Presidio is used for candidate generation only.** Its registry is trimmed to
the spaCy recognizer and its own arbitration and result-filtering are unused.
Its `validate_result()` returns a bool and *deletes* the loser — no tier, no
reason, no rejected candidate — which would destroy the thing this project is
built to show. Its stock output on one servicing sentence also includes `US_SSN`
at 0.4 with no SSA arithmetic behind it, `DATE_TIME` over a credit card number,
and `ORGANIZATION` over the literal word "SSN". A test asserts none of it
reaches arbitration.

---

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m spacy download en_core_web_md

pytest                                    # 176 tests
uvicorn app.main:app --port 8000          # demo at http://localhost:8000
```

Regenerate the corpus (deterministic from the seed):

```bash
python -m synth.generate --seed 42 --n 500 --out data/corpus/dev
python tools/check_frozen_corpus.py       # asserts the frozen set still reproduces
```

Container:

```bash
docker build -t mortgage-pii .
docker run --network none -p 8000:8000 mortgage-pii
```

`--network none` is the point: the spaCy model is baked in at build time, so the
container must start with no egress at all.

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/detect` | Entities, rejected candidates with reasons, per-tier counts, timings |
| `POST` | `/v1/anonymize` | The above plus the redacted document |
| `GET` | `/v1/taxonomy` | Entity types, tiers, validators |
| `GET` | `/healthz` | Liveness — touches nothing |
| `GET` | `/readyz` | Readiness — fails until the detector is warm |

Every response carries the taxonomy version, engine identity, a request id,
per-stage timings, and the validator rejection rate.

---

## Limitations

What this does not do, and where it should not be trusted.

**The numbers describe synthetic data this project generated.** They are a
ceiling, not a guarantee. The corpus embodies assumptions about how servicing
documents are written, and a model evaluated on a distribution its author chose
is being graded on its own homework. It has never been run against a real
servicing file.

**Named entities are the weakest part, and they are the ones people assume work.**
`CITY` recall is 0.803 — spaCy misses cities rather than mislabelling them.
`PERSON_NAME` is 0.959 here but that is on formulaic correspondence; adversarial
or unusual names are not represented.

**`US_ACCOUNT_NUM` is the weakest structured type at F1 0.778.** A bare
nine-digit account number that satisfies the SSA's rules is labelled `SSN`,
because tier outranks context proximity. The span is still redacted, so the
privacy outcome is unaffected — the label is wrong. Three arbitration orderings
were measured and tier-first won each time; this is its documented cost.

**Detection is format-dependent in ways the corpus does not punish.** `DATE`
matches numeric dates only, so "the fifteenth of March" is missed — and the
corpus contains no prose dates, so the reported `DATE` F1 of 1.000 overstates
real-world performance. `PHONE` requires visible formatting, so a bare
ten-digit number is missed. `SSN` requires a nearby label, so an unlabelled SSN
in a bare table column is missed.

**`MERS_MIN` carries more specification risk than its siblings.** Unlike Luhn
and the ABA checksum there is no convenient public corpus of known-good MINs to
test against, so generator and validator could in principle share a misreading.
They are written to be independent — the generator constructs check digits
forward and never calls the validator — but the risk is real and is flagged in
the taxonomy.

**English, US, one locale.** No multilingual support.

**Not yet measured:** throughput, p95 latency, cost per 1,000 documents, drift.
The service is instrumented for all four — per-stage timings, a batch-shaped
pipeline signature, taxonomy versioning, and the validator rejection rate are
all in place — but no benchmark has been run and no number is claimed.

**The container has not been built on this machine** (Docker is not installed
here). The Dockerfile and its CI job are written but unverified locally.

---

## Data provenance

**All data is synthetic.** Generated locally by `synth/` from committed
templates; no real borrower record has ever been in this repository. Identifiers
are structurally valid and randomly generated with no linkage to any person.
Phone numbers use the 555-0100–555-0199 range reserved for fictional use, email
domains are RFC 2606 reserved, and card numbers build on published processor
test prefixes.

Tier-1 identifiers are checksum-*correct* on purpose. A corpus of deliberately
broken identifiers would make every tier-1 validator reject every true positive,
and recall would collapse for a reason that looks like a detection bug.

---

## Layout

```
taxonomy/entities.yaml   19 entity types: tier, pattern, validator, examples.
                         Single source of truth for validation, generation,
                         the eval label set, and the drift bin space.
app/validate/            checksums.py (tier 1), structural.py (tier 2)
app/detect/              taxonomy scanners; Presidio behind a Protocol
app/core/                arbitration, anonymisation, pipeline, types
synth/                   templates and the deterministic generator
tests/                   176 tests; fixtures/ holds externally sourced vectors
tools/                   scoring probe, corpus check, sample generator
data/corpus/frozen/      committed reference set, CI gates on it
```

Validators are tested against **externally sourced** vectors — ten published
Federal Reserve routing numbers, ten published processor test cards, the SSA's
never-issued ranges, the IRS unassigned prefix table — not against values this
project generates. If the only evidence a validator were correct came from our
own generator, a shared misreading of a specification would be invisible in
both.

## Next

The regression gate is stubbed in `.github/workflows/ci.yml` and deliberately
disabled until `baseline.json` exists. It will gate on per-class floors as well
as micro-F1: a gate on the aggregate alone would pass a run that quietly lost 37
points of precision on a single type.

See [DECISIONS.md](DECISIONS.md) for why things are the way they are.
