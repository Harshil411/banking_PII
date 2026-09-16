"""The detector interface.

Detectors generate *candidates*. They do not validate, they do not resolve
overlaps, and they do not decide what survives -- those are the pipeline's
jobs, deliberately kept outside any library so the decisions stay inspectable
and the engine stays swappable.

That separation is what lets the evaluation harness compare engines: every
implementation of this Protocol sees the same input and produces the same
shape of output, so the only thing that varies between two runs is the
detector named by ``PII_DETECTOR``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.core.types import Candidate


@runtime_checkable
class Detector(Protocol):
    """Produces candidate spans for a document."""

    name: str
    version: str

    def detect(self, text: str, entity_types: set[str] | None = None) -> list[Candidate]:
        """Return candidates, in no guaranteed order.

        ``entity_types`` restricts the search when given. Overlapping and
        contradictory candidates are expected and are the arbiter's problem.
        """
        ...

    def warm(self) -> None:
        """Load any model weights.

        Called once from the application's lifespan handler. If model loading
        happened on first request instead, the first request would carry it
        and every p95 measurement taken afterwards would be wrong.
        """
        ...
