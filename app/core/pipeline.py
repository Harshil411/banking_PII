"""Orchestration: detect, validate, arbitrate, anonymise.

``analyze`` takes a *list* of texts even though the current API passes one.
That is deliberate. Throughput measured one request at a time is a latency
measurement in costume, and spaCy's real throughput comes from batching
through ``nlp.pipe``. Designing the signature for a batch now means the
benchmark harness and a future batch endpoint need no change here.

There are no module-level mutable singletons. v1 kept its pipelines and
compiled patterns in globals, which is what would stop an evaluation harness
importing this module and running it in-process -- and in-process evaluation
is 10-100x faster to iterate on than driving it over HTTP. Throughput gets
measured over HTTP separately, because that is the number that is true.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from app.core.anonymize import RedactionPolicy, anonymize
from app.core.arbitration import (
    arbitrate,
    counts_by_tier,
    counts_by_type,
    is_fragment,
)
from app.core.taxonomy import Taxonomy
from app.core.types import Entity, ValidationStatus
from app.detect.base import Detector


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    """Everything one document produced, including what was rejected and why."""

    request_id: str
    taxonomy_version: str
    engine: dict[str, str]
    entities: list[Entity]
    dropped: list[Entity]
    counts_by_tier: dict[str, int]
    counts_by_type: dict[str, int]
    timing_ms: dict[str, float]
    redacted: str | None = None

    @property
    def rejection_rate(self) -> float:
        """Share of validated candidates a validator rejected.

        Tracked from the first version because it is the drift signal this
        design makes available and label-mix PSI does not: a sudden rise in
        validator rejections says the input distribution moved before any
        label distribution has visibly shifted.

        The numerator is readings whose validator returned FAIL, and nothing
        else. ``dropped`` also holds valid readings that lost an overlap;
        counting those *as rejections* made the rate 0.33 on a sentence where
        nothing failed validation. Fragments of a longer match are left out of
        both halves: "0165" at the end of a valid phone number fails the NMLS
        rules only because it is a piece of something else.

        The denominator is every reading a validator ran on, kept or dropped,
        passing or failing. Tier-3 readings have no validator and would only
        dilute it. Counting per reading rather than per string is a choice:
        "credit account 666121234" near an SSN context word is one failed SSN
        reading and one passing account reading, so 0.5. Per string it would
        be 0.0, because the account reading survived -- and the failed SSN
        reading, which is the drift signal, would vanish. The cost is that the
        denominator still grows with how many readings overlap a value; per-type
        failure rates would remove that, and are the better metric to build
        when drift monitoring is built.
        """
        validated = [
            e
            for e in (*self.entities, *self.dropped)
            if e.validation_status is not ValidationStatus.NOT_APPLICABLE and not is_fragment(e)
        ]
        failed = sum(e.validation_status is ValidationStatus.FAIL for e in validated)
        return failed / len(validated) if validated else 0.0


@dataclass(slots=True)
class Pipeline:
    """Detect, validate, arbitrate. Anonymisation is opt-in per call."""

    taxonomy: Taxonomy
    detector: Detector
    policy: RedactionPolicy = field(default_factory=RedactionPolicy)

    def warm(self) -> None:
        self.detector.warm()

    def analyze(
        self,
        texts: list[str],
        entity_types: set[str] | None = None,
        redact: bool = False,
        request_id: str | None = None,
    ) -> list[AnalysisResult]:
        results = []
        for index, text in enumerate(texts):
            results.append(
                self._analyze_one(
                    text,
                    entity_types=entity_types,
                    redact=redact,
                    request_id=(
                        request_id
                        if request_id and len(texts) == 1
                        else f"{request_id or uuid.uuid4().hex[:12]}-{index}"
                    ),
                )
            )
        return results

    def _analyze_one(
        self,
        text: str,
        entity_types: set[str] | None,
        redact: bool,
        request_id: str,
    ) -> AnalysisResult:
        started = time.perf_counter()

        detect_start = time.perf_counter()
        candidates = self.detector.detect(text, entity_types)
        detect_ms = (time.perf_counter() - detect_start) * 1000

        # Validation and arbitration are one call because validation outcomes
        # are what arbitration ranks by; splitting them would mean validating
        # twice or passing partially-built entities around.
        arbitrate_start = time.perf_counter()
        kept, dropped = arbitrate(candidates, self.taxonomy)
        arbitrate_ms = (time.perf_counter() - arbitrate_start) * 1000

        redacted = None
        redact_ms = 0.0
        if redact:
            redact_start = time.perf_counter()
            redacted = anonymize(text, kept, self.policy, dropped=dropped)
            redact_ms = (time.perf_counter() - redact_start) * 1000

        total_ms = (time.perf_counter() - started) * 1000

        return AnalysisResult(
            request_id=request_id,
            taxonomy_version=self.taxonomy.version,
            engine={"name": self.detector.name, "version": self.detector.version},
            entities=kept,
            dropped=dropped,
            counts_by_tier=counts_by_tier(kept),
            counts_by_type=counts_by_type(kept),
            timing_ms={
                "detect": round(detect_ms, 3),
                "arbitrate": round(arbitrate_ms, 3),
                "redact": round(redact_ms, 3),
                "total": round(total_ms, 3),
            },
            redacted=redacted,
        )
