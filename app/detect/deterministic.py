"""Tier-1 and tier-2 detection: taxonomy regexes run over the whole document.

Scanners are intentionally permissive. Their job is recall -- find everything
that could be an instance of the type -- and the validators' job is precision.
A scanner that encodes its own correctness rules makes those rules unreachable
and hides near-misses from the validator that exists to reject them.

Context gating is the exception. A few types (LOAN_NUMBER, NMLS_ID,
CREDIT_SCORE) have patterns so broad that running them unguarded would claim
most of the numbers on a servicing page. For those the taxonomy declares
``context_words``, and a candidate is only emitted when one appears nearby.
"""

from __future__ import annotations

import re

from app.core.taxonomy import Taxonomy
from app.core.types import Candidate

#: How far either side of a match to look for a context word.
#:
#: Tuned on the corpus, not guessed. At 64 characters a single mention of
#: "loan number" vouched for every digit run in the following sentence --
#: routing numbers were labelled loan numbers, and a date's year was claimed
#: as an NMLS id from an "NMLS" two clauses away. 32 characters spans a label
#: and its value across a line break without reaching the next field.
CONTEXT_WINDOW = 32


class DeterministicDetector:
    """Regex scanning driven entirely by the taxonomy."""

    name = "deterministic"

    def __init__(self, taxonomy: Taxonomy, context_window: int = CONTEXT_WINDOW) -> None:
        self._taxonomy = taxonomy
        self._context_window = context_window
        self.version = taxonomy.version
        # Context words are matched on word boundaries, not as substrings.
        #
        # This is not fussiness. With plain substring matching "tin" (for
        # taxpayer identification number) matches inside "institution" -- and
        # "receiving institution routing number is ..." is exactly the
        # sentence where a routing number appears. SSN was gated in on every
        # wire instruction in the corpus and, being tier 1, then won the span
        # from ABA_ROUTING: measured SSN precision 0.236, ABA recall 0.022.
        #
        # Compiled once per type rather than per match per document.
        self._context: dict[str, re.Pattern[str]] = {
            name: re.compile(
                "|".join(rf"\b{re.escape(word.lower())}" for word in spec.context_words)
            )
            for name, spec in taxonomy.entities.items()
            if spec.context_words
        }

    def warm(self) -> None:
        """No-op: patterns are compiled when the taxonomy loads."""

    def detect(self, text: str, entity_types: set[str] | None = None) -> list[Candidate]:
        candidates: list[Candidate] = []
        lowered = text.lower()

        for name in self._taxonomy.scannable:
            if entity_types is not None and name not in entity_types:
                continue
            scanner = self._taxonomy.scanners[name]
            context = self._context.get(name)

            for match in scanner.finditer(text):
                start, end = match.start(), match.end()
                if start == end:
                    continue
                distance: int | None = None
                if context is not None:
                    distance = self._context_distance(lowered, start, end, context)
                    if distance is None:
                        continue
                candidates.append(
                    Candidate.from_span(
                        document=text,
                        entity_type=name,
                        start=start,
                        end=end,
                        score=1.0,
                        source=self.name,
                        pattern_name=name,
                        context_distance=distance,
                    )
                )
        return candidates

    def _context_distance(
        self, lowered_text: str, start: int, end: int, context: re.Pattern[str]
    ) -> int | None:
        """Characters to the nearest context word, or None if there is none.

        The distance matters, not just the presence. "Credit to account:
        169340608835 ... reference the loan number above" puts a context word
        for two different types within reach of one span; the nearer one is
        describing it.
        """
        window_start = max(0, start - self._context_window)
        window_end = min(len(lowered_text), end + self._context_window)

        best: int | None = None
        for match in context.finditer(lowered_text, window_start, window_end):
            if match.end() <= start:
                gap = start - match.end()
            elif match.start() >= end:
                gap = match.start() - end
            else:
                gap = 0
            if best is None or gap < best:
                best = gap
        return best
