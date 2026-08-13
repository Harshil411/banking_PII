# Banking PII Detection & Anonymization

**Local-first privacy service for banking text** — detects and anonymizes personally identifiable information (PII) using two Hugging Face token-classification models running entirely on your own machine. No data ever leaves the device.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-backend-009688?style=flat-square&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-frontend-61DAFB?style=flat-square&logo=react&logoColor=black)
![Hugging Face](https://img.shields.io/badge/Hugging%20Face-local%20models-FFD21E?style=flat-square&logo=huggingface&logoColor=black)

## Results

Latest validated run across 25 PII classes ([`metrics_summary 1.json`](metrics_summary%201.json); earlier run: [`metrics_summary.json`](metrics_summary.json)):

| Metric | Score |
|---|---|
| **Micro-F1 (overall)** | **0.866** |
| Precision | 0.812 |
| Recall | 0.928 |
| F1 — Aadhaar, driver's license, email | **1.00** |
| F1 — account number / PAN | 0.997 / 0.993 |

High recall on regulated identifiers is the design goal: in a privacy pipeline, a missed entity costs far more than a false positive.

## How it works

```
Banking text ──▶ PII extraction (token classification)
             ──▶ Schema cross-validation (regex + format rules per entity type)
             ──▶ Anonymized output
```

- **Extraction model** — `bert-base-multilingual-cased_100k_v1`: fine-tuned multilingual BERT for PII token classification
- **Anonymization model** — `llama-ai4privacy-multilingual-categorical-anonymiser-openpii_100k_v1`: category-aware PII replacement
- **Schema validation** — every detected entity is cross-checked against format rules in [`data_schema.json`](data_schema.json) (Aadhaar, PAN, IFSC, account numbers, credit cards, phone numbers, transaction IDs), making each detection inspectable and reducing false positives
- **React UI** — separate panels for extraction and anonymization, live metrics, and schema display

## Quick start

**Prerequisites:** Python 3.10+, Node.js 16+. Internet is only needed for the first install — models run locally at runtime. GPU is used if available (`torch.cuda.is_available()`), otherwise CPU.

### Backend

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```bash
cd frontend
npm install
npm start                        # opens http://localhost:3000
```

### Production

```bash
cd frontend && npm run build && cd ..
uvicorn backend.main:app --host 0.0.0.0 --port 8000
# open http://localhost:8000
```

## API

| Method | Endpoint | Body | Purpose |
|---|---|---|---|
| `POST` | `/api/bert/extract` | `{ text }` | Extract PII entities |
| `POST` | `/api/llama/anonymize` | `{ text, replacement="[REDACTED]" }` | Anonymize PII in text |
| `GET` | `/api/metrics` | — | Model performance metrics |
| `GET` | `/api/data_schema` | — | Entity schema and validation rules |

## Project structure

```
backend/            FastAPI service and model serving
frontend/           React UI (extraction / anonymization panels, metrics)
data_schema.json    Entity definitions, examples, and validation regexes
metrics_summary.json  Evaluation results across 32,017 labeled entities
test_*.py           Unit and validation tests (regex, tokenizer, cross-validation)
```

## Why local-first?

Banking PII cannot be sent to third-party APIs. This service is designed so inference, validation, and anonymization all happen on-device — suitable for sensitive text workflows where data residency is non-negotiable.

---

<sub>Built by [Harshil Agrawal](https://harshil-portfolio.duckdns.org/) · MS Data Science @ Virginia Tech</sub>
