"""Request and response models for the HTTP API.

Pydantic lives here and nowhere else. The core types are plain dataclasses
because they sit on the hot path; this is the boundary where input is
untrusted and validation is the point.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.core.pipeline import AnalysisResult
from app.core.types import Entity


class DetectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., description="Document to scan.")
    entity_types: list[str] | None = Field(
        default=None, description="Restrict the search to these types."
    )


class AnonymizeRequest(DetectRequest):
    redact_failed_tier1: bool = Field(
        default=False,
        description=(
            "Redact spans a tier-1 validator proved invalid. Off by default: "
            "redacting text we have positive evidence is not the entity is the "
            "false positive this design exists to avoid. Deployments that would "
            "rather over-redact than under-redact should turn it on."
        ),
    )


class EntityOut(BaseModel):
    entity_type: str
    start: int
    end: int
    text: str
    score: float
    source: str
    tier: int
    validation_status: str
    validator: str | None = None
    reason: str = ""

    @classmethod
    def of(cls, entity: Entity) -> EntityOut:
        return cls(
            entity_type=entity.entity_type,
            start=entity.start,
            end=entity.end,
            text=entity.text,
            score=round(entity.score, 4),
            source=entity.source,
            tier=int(entity.tier),
            validation_status=entity.validation_status.value,
            validator=entity.validator,
            reason=entity.reason,
        )


class DetectResponse(BaseModel):
    request_id: str
    taxonomy_version: str
    engine: dict[str, str]
    entities: list[EntityOut]
    dropped: list[EntityOut]
    counts_by_tier: dict[str, int]
    counts_by_type: dict[str, int]
    #: Share of validated candidates a validator rejected. Surfaced in the
    #: response because a rise here is an earlier drift signal than a shift in
    #: the label mix, and it is unique to a tiered design.
    rejection_rate: float
    timing_ms: dict[str, float]

    @classmethod
    def of(cls, result: AnalysisResult) -> DetectResponse:
        return cls(
            request_id=result.request_id,
            taxonomy_version=result.taxonomy_version,
            engine=result.engine,
            entities=[EntityOut.of(e) for e in result.entities],
            dropped=[EntityOut.of(e) for e in result.dropped],
            counts_by_tier=result.counts_by_tier,
            counts_by_type=result.counts_by_type,
            rejection_rate=round(result.rejection_rate, 4),
            timing_ms=result.timing_ms,
        )


class AnonymizeResponse(DetectResponse):
    redacted: str

    @classmethod
    def of(cls, result: AnalysisResult) -> AnonymizeResponse:
        base = DetectResponse.of(result)
        return cls(**base.model_dump(), redacted=result.redacted or "")


class EntitySpecOut(BaseModel):
    name: str
    tier: int
    description: str
    validator: str | None
    regex: str | None
    examples: list[str]
    context_words: list[str]


class TaxonomyResponse(BaseModel):
    version: str
    entities: list[EntitySpecOut]


class HealthResponse(BaseModel):
    status: str
    taxonomy_version: str | None = None
    engine: str | None = None
    detail: str | None = None
