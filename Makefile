# Common tasks. Every target runs from the repository root with the project
# virtualenv, so `make eval` works without activating anything first.

PY      := .venv/bin/python
PORT    ?= 8000
ENGINE  ?= presidio

.PHONY: help install test lint serve corpus check-corpora eval eval-check baseline samples screenshots

help:           ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

install:        ## create .venv, install dev dependencies and the spaCy model
	python3 -m venv .venv
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -r requirements-dev.txt
	$(PY) -m spacy download en_core_web_md

test:           ## run the test suite
	$(PY) -m pytest -p no:warnings

lint:           ## ruff
	$(PY) -m ruff check app synth evaluation tests tools

serve:          ## run the API and demo page at http://localhost:$(PORT)
	$(PY) -m uvicorn app.main:app --port $(PORT) --reload

corpus:         ## regenerate the committed corpora (then run `make baseline` and `make samples`)
	$(PY) -m synth.generate --seed 20260915 --n 120 --out data/corpus/frozen
	$(PY) -m synth.generate --seed 20260916 --n 120 --templates holdout --out data/corpus/holdout

check-corpora:  ## assert the committed corpora still regenerate from their seeds
	PYTHONPATH=. $(PY) tools/check_corpora.py

eval:           ## score both splits and print per-type results
	$(PY) -m evaluation --engine $(ENGINE)

eval-check:     ## fail if anything regressed against evaluation/baseline.json
	$(PY) -m evaluation --engine $(ENGINE) --check --quiet

baseline:       ## record current numbers as the baseline (a deliberate act, commit the diff)
	$(PY) -m evaluation --engine $(ENGINE) --write-baseline --quiet

samples:        ## regenerate the demo page's sample documents from the frozen corpus
	PYTHONPATH=. $(PY) tools/make_samples.py

screenshots:    ## capture README screenshots (needs playwright; see tools/screenshots.py)
	PYTHONPATH=. $(PY) tools/screenshots.py
