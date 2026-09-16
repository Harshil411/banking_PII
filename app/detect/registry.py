"""Detector construction, selected by name.

An explicit table rather than dynamic import, for the same reason the
validator registry is: an unknown name should fail at startup with a list of
what is valid, not at request time with an ImportError.

The names here are what ``PII_DETECTOR`` accepts, and they are what lets the
evaluation harness compare engines without touching any code.
"""

from __future__ import annotations

from app.core.taxonomy import Taxonomy
from app.core.types import Candidate
from app.detect.base import Detector
from app.detect.deterministic import DeterministicDetector


class CompositeDetector:
    """Runs several detectors and concatenates their candidates.

    No merging happens here. Overlaps and contradictions between detectors are
    the arbiter's business, and resolving them early -- inside a detector, or
    inside a library -- is how the reasoning becomes invisible.
    """

    def __init__(self, name: str, detectors: list[Detector]) -> None:
        self.name = name
        self._detectors = detectors
        self.version = "+".join(d.version for d in detectors)

    def warm(self) -> None:
        for detector in self._detectors:
            detector.warm()

    def detect(self, text: str, entity_types: set[str] | None = None) -> list[Candidate]:
        candidates = []
        for detector in self._detectors:
            candidates.extend(detector.detect(text, entity_types))
        return candidates


def build_detector(name: str, taxonomy: Taxonomy, spacy_model: str = "en_core_web_md") -> Detector:
    """Construct the named detector."""
    if name == "deterministic":
        return DeterministicDetector(taxonomy)

    if name == "presidio":
        from app.detect.presidio_detector import PresidioDetector

        return CompositeDetector(
            "presidio",
            [DeterministicDetector(taxonomy), PresidioDetector(taxonomy, spacy_model)],
        )

    raise ValueError(
        f"unknown detector {name!r}; available detectors are 'deterministic', 'presidio'"
    )
