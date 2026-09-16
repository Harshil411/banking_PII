# Multi-stage. The builder compiles wheels and downloads the spaCy model; the
# runtime carries neither pip's cache nor a compiler.
#
# Python 3.12 rather than 3.14: spaCy's compiled dependencies (thinc, blis,
# murmurhash) publish 3.12 wheels for every platform, and a container that
# falls back to building them from source is a slow, fragile build.
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Baked at build time, not fetched on boot. v1 called
# AutoTokenizer.from_pretrained() against the HuggingFace Hub inside its
# startup handler with no local_files_only, so a container with restricted
# egress hung during startup instead of failing. `docker run --network none`
# must reach /readyz 200.
ARG SPACY_MODEL=en_core_web_md
RUN python -m spacy download ${SPACY_MODEL}


FROM python:3.12-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PII_DETECTOR=presidio \
    PII_TAXONOMY_PATH=/srv/taxonomy/entities.yaml \
    PII_EVALUATION_PATH=/srv/evaluation/baseline.json \
    PII_HOST=0.0.0.0 \
    PII_PORT=8000

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin service

COPY --from=builder /opt/venv /opt/venv

WORKDIR /srv
COPY app/ ./app/
COPY taxonomy/ ./taxonomy/
# Only the committed numbers, served at /v1/evaluation; the harness itself and
# the corpora it scores do not ship.
COPY evaluation/baseline.json ./evaluation/baseline.json

# PII_TAXONOMY_PATH is set explicitly above rather than relying on the default
# derived from the package directory. Inside the image app/ and taxonomy/ are
# siblings under /srv, which happens to match, but depending on that
# coincidence is how a layout change becomes a silent startup failure.

USER service
EXPOSE 8000

# Liveness only. Readiness is /readyz and is the orchestrator's business:
# restarting a container that is still loading the model would never let it
# finish.
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=2).status==200 else 1)"

# No --reload, and one worker. Concurrency is the deployment's decision, and
# the benchmark measures a known worker count rather than an accidental one.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
