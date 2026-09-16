# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Working agreement

**Harshil writes the code in this repo.** Claude explains concepts, reviews diffs, argues against choices, and generates boring scaffolding (README skeletons, test fixtures, YAML, empty templates). Do not write implementation code unless scaffolding is explicitly requested — describe the fix and let him write it.

The reason is self-interest, not principle: this project exists to be interrogated in interviews. Its value is the ability to answer "why p95 and not mean?", "why that drift metric?", "what happens when the model degrades in production?" Code he did not write invites exactly those questions and cannot answer them.

`DECISIONS.md` holds one short hand-written, dated paragraph per real choice. It is interview prep, not documentation — never generate its entries.

## What this is

A local-first PII detection and anonymization service for Indian banking text. Two Hugging Face token-classification models run on-device (no third-party API calls — this is a hard design constraint, see README "Why local-first?"), and every model detection is cross-checked against per-entity regex rules before it is reported.

## Commands

Run all Python commands from the repository root — every script resolves `data_schema.json`, `metrics_summary*.json`, and the model directories as paths relative to CWD or to `Path(__file__).parents[1]`.

```bash
# Backend (main API — this is the one the README and frontend proxy target)
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend (dev; package.json proxies to localhost:8000)
cd frontend && npm install && npm start      # http://localhost:3000

# Production: build the React app, then serve it from FastAPI at :8000
cd frontend && npm run build && cd .. && uvicorn backend.main:app --port 8000
```

### Tests

Tests are standalone scripts, not a pytest suite — each has an `if __name__ == "__main__":` block and prints results rather than asserting. Run one at a time from the repo root:

```bash
python tests/test_cross_validation.py      # schema regex + cross-validation logic, no models needed
python tests/test_improved_regex.py        # regex precision experiments, no models needed
python tests/test_regex_improvements.py    # ditto
python tests/test_bert.py                  # requires the BERT model directory
python tests/test_tokenizer.py             # requires the LLaMA model directory
python tests/test_validated_detection.py   # HTTP integration test; needs a server on :8000 first
```

`tests/test_enhanced_detection.py` does a bare `from enhanced_pii_detector import EnhancedPIIDetector`, but that module lives in `scripts/`. It only runs with `PYTHONPATH=scripts`.

`npm test` in `frontend/` runs react-scripts/Jest, but no test files exist there yet.

## Model weights are not in the repo

`bert-base-multilingual-cased_100k_v1/` and `llama-ai4privacy-multilingual-categorical-anonymiser-openpii_100k_v1/` are gitignored and **absent from a fresh clone**. Startup does not fail without them: `load_models()` catches the exception, leaves `_bert_pipe`/`_llama_pipe` as `None`, and the model endpoints then return 503. So the server boots and `/api/health`, `/api/metrics`, `/api/data_schema` work, while `/api/bert/extract` and `/api/llama/anonymize` do not. Check `/api/health` before assuming an inference bug is a code bug.

## Architecture

### Detection pipeline

```
text ──▶ token-classification pipeline (aggregation_strategy="first")
     ──▶ _predict(): re-slices entity text from the ORIGINAL string via start/end offsets
     ──▶ validate_entity(): regex from data_schema.json for the predicted category
     ──▶ valid → entities[]  |  invalid → filtered_entities[] with a reason
     ──▶ _anonymize(): replaces spans back-to-front so indices stay valid
```

Two details that are load-bearing and easy to break:

- `_predict` deliberately ignores the pipeline's `word` field and reconstructs text as `original_text[start:end]`. The tokenizer emits subword artifacts (`##`), so trusting `word` re-breaks email and multi-token entity extraction.
- `_anonymize` sorts entities by `start` descending before substituting. Forward replacement invalidates every later offset.

### Schema cross-validation

[data_schema.json](data_schema.json) holds 22 entity categories, each `{examples, regex}`; [data_schema_description.txt](data_schema_description.txt) is the human-readable mirror of the same rules and must be kept in sync when a regex changes. Patterns are anchored (`^...$`) and used with `.match()` on the full entity span — they are validators, not scanners.

When a detection fails its own category's pattern, [backend/main.py](backend/main.py) tries a *cross-validation* pass: it walks a hardcoded `specific_categories` list first (PAN, TELEPHONENUM, AADHAAR, …) and relabels the entity to whichever category's pattern it actually matches, recording `original_category` and `corrected_category`. `STREET` (and any `.*` pattern) is excluded from the fallback sweep because it matches everything. If you add a broad-matching category to the schema, it must be excluded here too or cross-validation will relabel everything to it.

This is what suppresses the false positives the `docs/` notes were written about — model-only output tags fragments like `1234 - 5678` as AADHAAR; schema validation drops them.

### Three backend variants — main.py is the live one

| File | App title | Endpoints |
|---|---|---|
| [backend/main.py](backend/main.py) | v1.0.0 | **superset**: `/api/bert/extract`, `/api/llama/anonymize`, `/api/validated/{detect,anonymize}`, `/api/metrics`, `/api/data_schema`, `/api/health`, static frontend mount |
| [backend/validated_enhanced_main.py](backend/validated_enhanced_main.py) | v3.0.0 | `/api/validated/*` only — no `/api/metrics`; validation logic lives in a `ValidatedEnhancedPIIDetector` class |
| [backend/enhanced_main.py](backend/enhanced_main.py) | v2.0.0 | `/api/enhanced/*` — earlier iteration, nothing in the frontend calls it |

`main.py` folded the validated logic in as module-level functions and is what the React app and the README use. The other two are prior iterations kept for reference; treat `main.py` as the source of truth and don't assume a fix in one propagates. [start_validated_server.py](start_validated_server.py) launches `validated_enhanced_main` specifically, so a server started that way has no `/api/metrics` and the Metrics panel will error.

`scripts/` holds the same detection logic again as importable classes plus one-off demo/repair scripts (`fix_tokenizer.py`, `fix_llama_tokenizer.py` patch corrupted local tokenizer files). Not imported by the backend.

### Tokenizer loading fallback chain

`_load_token_classifier` exists because the LLaMA checkpoint's `tokenizer.json` is corrupt. For any path containing "llama" it loads the model weights and pairs them with a downloaded `bert-base-multilingual-cased` tokenizer; otherwise it walks six `trust_remote_code`/`use_fast`/`local_files_only` combinations until one succeeds. That fallback needs network on first run, and is the one place the "fully local" property depends on a prior download.

### Frontend

Two frontends coexist. The React app under [frontend/src/](frontend/src/) is the real one: `App.js` holds tab state plus the Hindi/English banking sample texts, and broadcasts sample selection through a `window` CustomEvent (`sampleTextSelected`) rather than props. The flat [frontend/app.js](frontend/app.js) + [frontend/index.html](frontend/index.html) are a vanilla-JS prototype, served only as a fallback when `frontend/build/` is absent.

Panels do not route API calls uniformly — `BertPanel`, `LlamaPanel`, and `MetricsPanel` go through [frontend/src/services/api.js](frontend/src/services/api.js) (axios, absolute `http://localhost:8000` base or `REACT_APP_API_URL`), while `EnhancedPanel` uses bare `fetch('/api/validated/...')` relying on the CRA dev proxy. The two disagree in production; prefer `services/api.js` for new calls.

### Metrics

`/api/metrics` returns a dict keyed by file path, collecting whichever of its candidate files exist. Two stale references: it looks for `metrics_summary 1.json`, which was renamed to `metrics_summary_validated.json` (commit f5c4510) and so is never picked up, and the README links the old name too. `metrics_summary_validated.json` holds the current validated run (0.866 micro-F1); `metrics_summary.json` is the earlier one.

## Docs

`docs/*.md` are dated change notes from previous fixes (false positives, email extraction, metrics panel errors, UI iterations), not current specifications. Useful for "why is this code shaped this way", misleading as a description of present behavior.
