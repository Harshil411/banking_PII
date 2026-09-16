"""Tier-3 candidate generation via Presidio's spaCy recognizer.

Presidio does two jobs. Its recognizer catalogue generates candidates, which
is useful. Its ``AnalyzerEngine`` also arbitrates overlapping spans by score
and silently deletes anything a recognizer's ``validate_result`` rejects,
which is precisely the decision this project exists to own and make visible.
So the registry is trimmed to the spaCy NER recognizer and nothing else, and
everything downstream of candidate generation is ours.

That is not a theoretical concern. Presidio's stock output on a servicing
sentence includes:

    US_SSN            '457551275'          score=0.4    (regex, no SSA rules)
    US_BANK_NUMBER    '457551275'          score=0.05
    US_PASSPORT       '457551275'          score=0.05
    US_DRIVER_LICENSE '457551275'          score=0.01
    DATE_TIME         '4111111111111111'   score=0.85   (a credit card)
    ORGANIZATION      'SSN'                score=0.85   (the label text)

Four recognizers claiming one nine-digit run at token scores, a payment card
labelled as a date, and the word "SSN" labelled an organisation. Admitting any
of that would corrupt precision in a way that looks like a model problem.

DATE_TIME is deliberately not taken from spaCy. Besides matching credit card
numbers, its spans absorb trailing words ("March 3, 2024 about"). Dates come
from the taxonomy regex instead, which means prose dates are not detected --
a real limitation, recorded in the README rather than hidden.
"""

from __future__ import annotations

import logging

from app.core.taxonomy import Taxonomy
from app.core.types import Candidate
from app.validate.structural import us_state

logger = logging.getLogger(__name__)

#: Presidio entity types worth taking, mapped onto taxonomy labels. LOCATION
#: is resolved to CITY or US_STATE by closed-set membership, because spaCy
#: labels both as GPE and something has to disambiguate them.
PRESIDIO_TO_TAXONOMY: dict[str, str] = {
    "PERSON": "PERSON_NAME",
    "LOCATION": "CITY",
}

#: Characters spaCy routinely includes at a span edge that are not part of the
#: entity. Trimming them keeps offsets honest and stops "Sacramento," and
#: "Sacramento" being counted as different answers.
_EDGE = " \t\n\r.,;:!?\"'()[]"


class PresidioDetector:
    """spaCy-backed NER for the model-carried types, with everything else off."""

    name = "presidio"

    def __init__(self, taxonomy: Taxonomy, spacy_model: str = "en_core_web_md") -> None:
        self._taxonomy = taxonomy
        self._spacy_model = spacy_model
        self._analyzer = None
        self.version = f"presidio+{spacy_model}"

    def warm(self) -> None:
        """Build the analyzer and load the spaCy model.

        Called from the lifespan handler. Loading on first request instead
        would put several hundred milliseconds of model initialisation inside
        one request and make every latency percentile measured afterwards a
        fiction.
        """
        if self._analyzer is not None:
            return

        from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
        from presidio_analyzer.nlp_engine import NlpEngineProvider
        from presidio_analyzer.predefined_recognizers import SpacyRecognizer

        provider = NlpEngineProvider(
            nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": self._spacy_model}],
            }
        )
        registry = RecognizerRegistry()
        registry.add_recognizer(SpacyRecognizer(supported_language="en"))

        self._analyzer = AnalyzerEngine(
            nlp_engine=provider.create_engine(),
            registry=registry,
            supported_languages=["en"],
            default_score_threshold=0.0,
        )
        logger.info("presidio analyzer ready with %s", self._spacy_model)

    @property
    def is_warm(self) -> bool:
        return self._analyzer is not None

    def detect(self, text: str, entity_types: set[str] | None = None) -> list[Candidate]:
        if self._analyzer is None:
            self.warm()
        assert self._analyzer is not None

        wanted = set(PRESIDIO_TO_TAXONOMY)
        results = self._analyzer.analyze(text=text, language="en", entities=sorted(wanted))

        candidates: list[Candidate] = []
        for result in results:
            if result.entity_type not in PRESIDIO_TO_TAXONOMY:
                # Defensive: the registry should make this unreachable, and a
                # test asserts it. If it ever fires, a stock recognizer has
                # crept back in and precision is about to move for reasons
                # that will look like a model regression.
                logger.warning("discarding unexpected presidio type %s", result.entity_type)
                continue

            start, end = self._trim(text, result.start, result.end)
            if start >= end:
                continue

            entity_type = self._resolve(text[start:end], PRESIDIO_TO_TAXONOMY[result.entity_type])
            if entity_types is not None and entity_type not in entity_types:
                continue
            if entity_type not in self._taxonomy:
                continue

            candidates.append(
                Candidate.from_span(
                    document=text,
                    entity_type=entity_type,
                    start=start,
                    end=end,
                    score=float(result.score),
                    source=self.name,
                    pattern_name=result.entity_type,
                )
            )
        return candidates

    @staticmethod
    def _resolve(surface: str, default_type: str) -> str:
        """Split spaCy's single LOCATION label into CITY and US_STATE."""
        if default_type == "CITY" and us_state(surface)[0]:
            return "US_STATE"
        return default_type

    @staticmethod
    def _trim(text: str, start: int, end: int) -> tuple[int, int]:
        """Trim edge punctuation and stop the span at a line break.

        spaCy's NER routinely runs a PERSON span across a newline into the
        next field of a structured document: in

            Prepared for: Maria Delgado
            Loan number: 0012345678

        the PERSON span covered "Maria Delgado\nLoan", which then redacted
        the word "Loan" out of the following label. Entity mentions of these
        types do not contain line breaks, so the span is cut at the first one.
        """
        newline = text.find("\n", start, end)
        if newline != -1:
            end = newline

        while start < end and text[start] in _EDGE:
            start += 1
        while end > start and text[end - 1] in _EDGE:
            end -= 1
        return start, end
