"""Loader for ``taxonomy/entities.yaml``.

The taxonomy is the single source of truth for runtime validation, synthetic
generation, the evaluation label set, and the drift bin space. Everything
downstream assumes it is coherent, so this module's job is to refuse to
produce an incoherent one.

It raises rather than warns. v1's habit was to guard every file read with
``.exists()`` and degrade to an empty dict, so a misconfigured deployment
returned ``{"schema": null}`` and looked like an empty result rather than a
broken service. A taxonomy that cannot be loaded is not a degraded service,
it is a service that should not start.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.types import Tier
from app.validate.registry import Validator
from app.validate.registry import get as get_validator


class TaxonomyError(ValueError):
    """Raised when the taxonomy file is malformed or internally inconsistent."""


class EntitySpec(BaseModel):
    """One entity type."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    name: str
    tier: Tier
    description: str
    regex: str | None = None
    validator: str | None = None
    generator: str
    examples: list[str] = Field(default_factory=list)
    counter_examples: list[str] = Field(default_factory=list)
    context_words: list[str] = Field(default_factory=list)
    #: Template with a single "{}" slot, used by the taxonomy contract test to
    #: embed examples for patterns that depend on lookaround context.
    test_context: str | None = None

    @model_validator(mode="after")
    def _check_tier_coherence(self) -> EntitySpec:
        if self.tier in (Tier.ARITHMETIC, Tier.STRUCTURAL) and self.validator is None:
            raise TaxonomyError(
                f"{self.name}: tier {int(self.tier)} means a deterministic rule exists, "
                "so a validator is required"
            )
        if self.tier is Tier.CONTEXTUAL and self.validator is not None:
            raise TaxonomyError(
                f"{self.name}: tier 3 means no rule can confirm the span, but a validator "
                f"({self.validator!r}) is declared; promote the entity or drop the validator"
            )
        if self.regex is None and self.tier is not Tier.CONTEXTUAL:
            raise TaxonomyError(
                f"{self.name}: only tier-3 entities may be purely model-carried, "
                f"but tier {int(self.tier)} declares no regex"
            )
        return self

    @property
    def is_model_carried(self) -> bool:
        return self.regex is None

    @property
    def is_context_gated(self) -> bool:
        return bool(self.context_words)


class Taxonomy(BaseModel):
    """The full entity taxonomy, with patterns compiled and validators resolved."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    version: str
    entities: dict[str, EntitySpec]
    scanners: dict[str, re.Pattern[str]]
    anchored: dict[str, re.Pattern[str]]
    validators: dict[str, Validator]
    #: Declaration order, used as the final deterministic tiebreak in arbitration.
    order: dict[str, int]

    def __getitem__(self, name: str) -> EntitySpec:
        return self.entities[name]

    def __contains__(self, name: str) -> bool:
        return name in self.entities

    def __iter__(self):  # type: ignore[override]
        return iter(self.entities.values())

    def tier_of(self, name: str) -> Tier:
        return self.entities[name].tier

    def validator_for(self, name: str) -> tuple[str | None, Validator | None]:
        spec = self.entities[name]
        if spec.validator is None:
            return None, None
        return spec.validator, self.validators[name]

    def names_by_tier(self, tier: Tier) -> list[str]:
        return [n for n, s in self.entities.items() if s.tier is tier]

    @property
    def scannable(self) -> list[str]:
        return [n for n, s in self.entities.items() if not s.is_model_carried]

    @property
    def model_carried(self) -> list[str]:
        return [n for n, s in self.entities.items() if s.is_model_carried]


def load_taxonomy(
    path: str | Path,
    known_generators: set[str] | None = None,
) -> Taxonomy:
    """Parse, validate and compile the taxonomy at ``path``.

    ``known_generators`` is optional because the service does not need the
    synthetic generator to run. When supplied -- by the test suite, which
    passes ``synth.providers.PROVIDERS`` -- every declared generator name is
    checked, so a typo in the taxonomy cannot survive to generation time.
    """
    path = Path(path)
    if not path.is_file():
        raise TaxonomyError(f"taxonomy file not found: {path}")

    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TaxonomyError(f"{path}: expected a mapping at the top level")

    version = raw.get("version")
    if not isinstance(version, str) or not version:
        raise TaxonomyError(f"{path}: a non-empty string `version` is required")

    raw_entities = raw.get("entities")
    if not isinstance(raw_entities, dict) or not raw_entities:
        raise TaxonomyError(f"{path}: a non-empty `entities` mapping is required")

    entities: dict[str, EntitySpec] = {}
    scanners: dict[str, re.Pattern[str]] = {}
    anchored: dict[str, re.Pattern[str]] = {}
    validators: dict[str, Validator] = {}
    order: dict[str, int] = {}

    for index, (name, body) in enumerate(raw_entities.items()):
        if not isinstance(body, dict):
            raise TaxonomyError(f"{name}: expected a mapping, found {type(body).__name__}")
        try:
            spec = EntitySpec(name=name, **body)
        except TaxonomyError:
            raise
        except Exception as exc:
            raise TaxonomyError(f"{name}: {exc}") from exc

        if spec.regex is not None:
            try:
                scanners[name] = re.compile(spec.regex)
            except re.error as exc:
                raise TaxonomyError(f"{name}: regex does not compile: {exc}") from exc
            # The anchored form is derived, never authored. Maintaining two
            # patterns by hand is how they drift apart.
            anchored[name] = re.compile(rf"\A(?:{spec.regex})\Z")

        if spec.validator is not None:
            try:
                validators[name] = get_validator(spec.validator)
            except KeyError as exc:
                raise TaxonomyError(f"{name}: {exc.args[0]}") from None

        if known_generators is not None and spec.generator not in known_generators:
            raise TaxonomyError(
                f"{name}: unknown generator {spec.generator!r}; registered generators are "
                f"{', '.join(sorted(known_generators))}"
            )

        entities[name] = spec
        order[name] = index

    return Taxonomy(
        version=version,
        entities=entities,
        scanners=scanners,
        anchored=anchored,
        validators=validators,
        order=order,
    )
