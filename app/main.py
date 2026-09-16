"""Application factory.

Model loading happens in the lifespan handler, not on first request. If it did
not, the first request would carry it and every latency percentile measured
afterwards would be a fiction -- and the p95 number is one of the four this
project exists to produce.
"""

from __future__ import annotations

import json
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import PACKAGE_ROOT, Settings, get_settings
from app.core.pipeline import Pipeline
from app.core.taxonomy import load_taxonomy
from app.detect.registry import build_detector

logger = logging.getLogger(__name__)

STATIC_DIR = PACKAGE_ROOT / "web" / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    app = FastAPI(
        title="Mortgage PII Service",
        version="0.1.0",
        description=(
            "PII detection and anonymisation for US mortgage and loan-servicing text. "
            "Every detection is checked against a validator whose strength is recorded "
            "as a tier, and rejected candidates are returned with the reason rather "
            "than discarded."
        ),
        lifespan=_lifespan,
    )
    app.state.settings = settings
    app.state.pipeline = None
    app.state.taxonomy = None
    app.state.startup_error = None
    app.state.evaluation = None

    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
        )

    app.middleware("http")(_security_headers)
    app.include_router(router)

    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="demo")

    return app


#: Paths served by FastAPI's own documentation pages, which load Swagger UI and
#: ReDoc from a CDN. The strict policy below would blank them.
_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")

#: Endpoints whose responses echo the submitted document. Nothing that contains
#: PII should be stored by a browser or an intermediary cache.
_SENSITIVE_PREFIXES = ("/v1/detect", "/v1/anonymize")


async def _security_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    headers = response.headers
    headers.setdefault("X-Content-Type-Options", "nosniff")
    headers.setdefault("Referrer-Policy", "no-referrer")
    if path.startswith(_SENSITIVE_PREFIXES):
        headers["Cache-Control"] = "no-store"
    if not path.startswith(_DOCS_PATHS):
        # No inline script or style anywhere in the demo, so the policy can be
        # strict: the page renders text users paste, and a CSP that forbids
        # inline execution is the backstop if escaping is ever got wrong.
        frame_ancestors = request.app.state.settings.frame_ancestors
        headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'none'; "
            f"frame-ancestors {frame_ancestors}",
        )
    return response


def _load_evaluation(settings: Settings) -> dict | None:
    path = settings.evaluation_path
    if not path.is_file():
        logger.info("no evaluation baseline at %s; /v1/evaluation disabled", path)
        return None
    return json.loads(path.read_text(encoding="utf-8"))


async def _lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    try:
        taxonomy = load_taxonomy(settings.taxonomy_path)
        detector = build_detector(settings.detector, taxonomy, settings.spacy_model)
        pipeline = Pipeline(taxonomy=taxonomy, detector=detector)

        logger.info("warming detector %r", settings.detector)
        pipeline.warm()

        app.state.evaluation = _load_evaluation(settings)
        app.state.taxonomy = taxonomy
        app.state.pipeline = pipeline
        logger.info(
            "ready: taxonomy %s, %d entity types, engine %s",
            taxonomy.version,
            len(taxonomy.entities),
            detector.name,
        )
    except Exception as exc:
        # Recorded and surfaced through /readyz rather than swallowed. v1
        # caught model-loading failures, left the pipelines as None, and went
        # on serving -- so a broken deployment looked like a service that
        # found no entities.
        app.state.startup_error = f"{type(exc).__name__}: {exc}"
        logger.exception("startup failed")

    yield


app = create_app()
