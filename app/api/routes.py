"""HTTP endpoints.

``/healthz`` and ``/readyz`` are separate on purpose. Liveness must answer
without touching the taxonomy or the model, so an orchestrator does not
restart a container that is merely still loading. Readiness must fail until
the detector is warm, so traffic is not routed to an instance whose first
request would carry several hundred milliseconds of model initialisation.
The demo page uses the same distinction to show a warming state rather than
appearing broken on a cold start.
"""

from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter, HTTPException, Request, status

from app.api.schemas import (
    AnonymizeRequest,
    AnonymizeResponse,
    DetectRequest,
    DetectResponse,
    EntitySpecOut,
    HealthResponse,
    TaxonomyResponse,
)
from app.core.anonymize import RedactionPolicy

router = APIRouter()


def _state(request: Request):
    state = request.app.state
    if getattr(state, "pipeline", None) is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="service is still starting",
        )
    return state


def _check_text(text: str, limit: int) -> None:
    size = len(text.encode("utf-8"))
    if size > limit:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"text is {size} bytes, limit is {limit}",
        )


def _check_types(requested: list[str] | None, state) -> set[str] | None:
    if requested is None:
        return None
    unknown = sorted(set(requested) - set(state.taxonomy.entities))
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unknown entity types: {', '.join(unknown)}",
        )
    return set(requested)


@router.post("/v1/detect", response_model=DetectResponse, tags=["detection"])
def detect(payload: DetectRequest, request: Request) -> DetectResponse:
    """Find PII in a document, reporting both what was kept and what was rejected."""
    state = _state(request)
    _check_text(payload.text, state.settings.max_text_bytes)
    result = state.pipeline.analyze(
        [payload.text], entity_types=_check_types(payload.entity_types, state)
    )[0]
    return DetectResponse.of(result)


@router.post("/v1/anonymize", response_model=AnonymizeResponse, tags=["detection"])
def anonymize(payload: AnonymizeRequest, request: Request) -> AnonymizeResponse:
    """Detect and return the document with every surviving entity replaced."""
    state = _state(request)
    _check_text(payload.text, state.settings.max_text_bytes)

    # A per-request copy, never a mutation: the pipeline is shared across
    # requests and test_the_policy_flag_does_not_leak_between_requests holds it.
    pipeline = state.pipeline
    if payload.redact_failed_tier1:
        pipeline = replace(pipeline, policy=RedactionPolicy(redact_failed_tier1=True))

    result = pipeline.analyze(
        [payload.text],
        entity_types=_check_types(payload.entity_types, state),
        redact=True,
    )[0]
    return AnonymizeResponse.of(result)


@router.get("/v1/taxonomy", response_model=TaxonomyResponse, tags=["taxonomy"])
def taxonomy(request: Request) -> TaxonomyResponse:
    """The entity taxonomy, including tiers. Drives the demo page's legend."""
    state = _state(request)
    return TaxonomyResponse(
        version=state.taxonomy.version,
        entities=[
            EntitySpecOut(
                name=spec.name,
                tier=int(spec.tier),
                description=" ".join(spec.description.split()),
                validator=spec.validator,
                regex=spec.regex,
                examples=spec.examples,
                context_words=spec.context_words,
            )
            for spec in state.taxonomy.entities.values()
        ],
    )


@router.get("/v1/evaluation", tags=["evaluation"])
def evaluation(request: Request) -> dict:
    """The committed evaluation baseline: the numbers CI gates on.

    Scored on synthetic documents this project generated, on two splits -- one
    built from the templates the rules were tuned against, one from templates
    never used while tuning.
    """
    state = _state(request)
    if state.evaluation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no evaluation baseline loaded")
    return state.evaluation


@router.get("/healthz", response_model=HealthResponse, tags=["operations"])
def healthz() -> HealthResponse:
    """Liveness. Deliberately touches nothing, so a slow start is not a restart."""
    return HealthResponse(status="ok")


@router.get("/readyz", response_model=HealthResponse, tags=["operations"])
def readyz(request: Request) -> HealthResponse:
    """Readiness. Fails until the taxonomy is loaded and the detector is warm."""
    state = request.app.state
    if getattr(state, "pipeline", None) is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=getattr(state, "startup_error", None) or "warming up",
        )
    return HealthResponse(
        status="ready",
        taxonomy_version=state.taxonomy.version,
        engine=state.pipeline.detector.name,
    )
