"""Contract tests for taxonomy/entities.yaml.

This is the highest-value test file in the repository, because it is the one
that would have caught both of v1's defects:

  * Every detection regex in v1 was double-escaped inside a Python raw string,
    so it compiled to a pattern that could never match. 76 of them shipped and
    silently matched nothing for the life of the project.
    -> caught by test_scanner_finds_its_own_examples_in_prose

  * v1 declared GIVENNAME and SURNAME as separate types with byte-identical
    regexes, asking the model to learn a distinction the schema said did not
    exist. They scored F1 0.46 and 0.12.
    -> caught by test_no_two_entities_share_a_pattern

The rest of the file enforces that each entity's examples, counter-examples,
pattern and validator actually agree with one another.
"""

from __future__ import annotations

import pytest

from app.core.taxonomy import EntitySpec, Taxonomy, TaxonomyError, load_taxonomy
from app.core.types import Tier
from app.validate.registry import VALIDATORS

GENERIC_CONTEXT = "Reference {} appears in the servicing record."


def _embed(spec: EntitySpec, value: str) -> tuple[str, int, int]:
    """Place ``value`` in context and return the text with the value's offsets."""
    template = spec.test_context or GENERIC_CONTEXT
    prefix, _, suffix = template.partition("{}")
    return prefix + value + suffix, len(prefix), len(prefix) + len(value)


def _entity_ids(taxonomy: Taxonomy) -> list[str]:
    return list(taxonomy.entities)


# --------------------------------------------------------------------------
# The two v1 regressions
# --------------------------------------------------------------------------


def test_scanner_finds_its_own_examples_in_prose(taxonomy):
    """Every scanner must locate its own examples, at exactly the right offsets.

    A pattern that matches nothing passes every "does it reject bad input"
    test ever written. The only way to catch it is to require that it finds
    something it is supposed to find, in text shaped like real input.
    """
    failures = []
    for name, spec in taxonomy.entities.items():
        if spec.is_model_carried:
            continue
        scanner = taxonomy.scanners[name]
        for example in spec.examples:
            text, start, end = _embed(spec, example)
            found = [m for m in scanner.finditer(text) if (m.start(), m.end()) == (start, end)]
            if not found:
                actual = [(m.group(0), m.start(), m.end()) for m in scanner.finditer(text)]
                failures.append(
                    f"{name}: expected {example!r} at ({start}, {end}) in {text!r}; "
                    f"scanner produced {actual}"
                )
    assert not failures, "scanner did not match its own examples:\n  " + "\n  ".join(failures)


def test_no_two_entities_share_a_pattern(taxonomy):
    """Two types with identical patterns declare a distinction that does not exist."""
    seen: dict[str, str] = {}
    collisions = []
    for name, spec in taxonomy.entities.items():
        if spec.regex is None:
            continue
        if spec.regex in seen:
            collisions.append(f"{seen[spec.regex]} and {name} share the pattern {spec.regex!r}")
        seen[spec.regex] = name
    assert not collisions, "identical patterns:\n  " + "\n  ".join(collisions)


# --------------------------------------------------------------------------
# Examples, counter-examples and validators must agree
# --------------------------------------------------------------------------


def test_every_entity_declares_examples(taxonomy):
    missing = [n for n, s in taxonomy.entities.items() if not s.examples]
    assert not missing, f"entities with no examples cannot be contract-tested: {missing}"


def test_examples_pass_their_own_validator(taxonomy):
    failures = []
    for name, spec in taxonomy.entities.items():
        if spec.validator is None:
            continue
        validator = taxonomy.validators[name]
        for example in spec.examples:
            ok, reason = validator(example)
            if not ok:
                failures.append(f"{name}: example {example!r} rejected by own validator: {reason}")
    assert not failures, "\n  ".join(failures)


def test_counter_examples_are_rejected(taxonomy):
    """A counter-example must be rejected by the pattern or by the validator."""
    failures = []
    for name, spec in taxonomy.entities.items():
        for counter in spec.counter_examples:
            matched = name in taxonomy.anchored and taxonomy.anchored[name].match(counter)
            if not matched and spec.test_context:
                text, start, end = _embed(spec, counter)
                matched = any(
                    (m.start(), m.end()) == (start, end)
                    for m in taxonomy.scanners[name].finditer(text)
                )
            if not matched:
                continue  # rejected by the pattern, which is a valid outcome
            if spec.validator is None:
                failures.append(
                    f"{name}: counter-example {counter!r} matches the pattern and there is "
                    "no validator to reject it"
                )
                continue
            ok, _ = taxonomy.validators[name](counter)
            if ok:
                failures.append(
                    f"{name}: counter-example {counter!r} matches the pattern and its "
                    "validator accepts it"
                )
    assert not failures, "\n  ".join(failures)


def test_every_validator_rejects_something_its_pattern_accepts(taxonomy):
    """A validator that only ever agrees with its pattern adds nothing.

    If this fails for an entity, the honest fix is to demote it to tier 3
    rather than keep a validator that is decorative.
    """
    failures = []
    for name, spec in taxonomy.entities.items():
        if spec.validator is None:
            continue
        proves_useful = False
        for counter in spec.counter_examples:
            matched = taxonomy.anchored[name].match(counter)
            if not matched and spec.test_context:
                text, start, end = _embed(spec, counter)
                matched = any(
                    (m.start(), m.end()) == (start, end)
                    for m in taxonomy.scanners[name].finditer(text)
                )
            if matched and not taxonomy.validators[name](counter)[0]:
                proves_useful = True
                break
        if not proves_useful:
            failures.append(
                f"{name}: no counter-example both matches the pattern and fails "
                f"validator {spec.validator!r}"
            )
    assert not failures, "\n  ".join(failures)


def test_rejection_reasons_are_human_readable(taxonomy):
    """Rejection reasons reach end users through the API and the demo UI."""
    for name, spec in taxonomy.entities.items():
        if spec.validator is None:
            continue
        for counter in spec.counter_examples:
            ok, reason = taxonomy.validators[name](counter)
            if not ok:
                assert len(reason) > 10, f"{name}: terse rejection reason {reason!r}"
                assert not reason.startswith("Traceback"), f"{name}: reason leaks a traceback"


# --------------------------------------------------------------------------
# Structural coherence
# --------------------------------------------------------------------------


def test_tier_one_and_two_have_validators(taxonomy):
    for name, spec in taxonomy.entities.items():
        if spec.tier in (Tier.ARITHMETIC, Tier.STRUCTURAL):
            assert spec.validator is not None, (
                f"{name} is tier {int(spec.tier)} without a validator"
            )


def test_tier_three_has_no_validator(taxonomy):
    """Tier 3 means no rule can confirm the span. A validator there is a category error."""
    for name, spec in taxonomy.entities.items():
        if spec.tier is Tier.CONTEXTUAL:
            assert spec.validator is None, f"{name} is tier 3 but declares {spec.validator!r}"


def test_only_tier_three_may_be_model_carried(taxonomy):
    for name, spec in taxonomy.entities.items():
        if spec.is_model_carried:
            assert spec.tier is Tier.CONTEXTUAL, f"{name} has no regex but is tier {int(spec.tier)}"


def test_no_unused_validators_in_registry(taxonomy):
    referenced = {s.validator for s in taxonomy.entities.values() if s.validator}
    orphans = set(VALIDATORS) - referenced
    assert not orphans, f"registered but unreferenced validators: {sorted(orphans)}"


def test_every_entity_has_a_description(taxonomy):
    for name, spec in taxonomy.entities.items():
        assert len(spec.description.strip()) > 40, f"{name}: description is too thin to be useful"


def test_declaration_order_is_total(taxonomy):
    """Arbitration's final tiebreak is declaration order, so it must be complete."""
    assert set(taxonomy.order) == set(taxonomy.entities)
    assert sorted(taxonomy.order.values()) == list(range(len(taxonomy.entities)))


def test_anchored_form_is_derived_from_the_scanner(taxonomy):
    for name in taxonomy.scanners:
        assert taxonomy.anchored[name].pattern == rf"\A(?:{taxonomy.entities[name].regex})\Z"


# --------------------------------------------------------------------------
# The loader refuses incoherent configurations
# --------------------------------------------------------------------------


def _write(tmp_path, body: str):
    path = tmp_path / "entities.yaml"
    path.write_text(body, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("entities:\n  X:\n    tier: 1\n", "version"),
        ('version: "1"\nentities: {}\n', "non-empty"),
        (
            'version: "1"\nentities:\n  X:\n    tier: 1\n    description: "d"\n'
            "    regex: 'a'\n    validator: nope\n    generator: g\n",
            "unknown validator",
        ),
        (
            'version: "1"\nentities:\n  X:\n    tier: 1\n    description: "d"\n'
            "    regex: '[unclosed'\n    validator: ssn\n    generator: g\n",
            "does not compile",
        ),
        (
            'version: "1"\nentities:\n  X:\n    tier: 1\n    description: "d"\n'
            "    regex: 'a'\n    generator: g\n",
            "validator is required",
        ),
        (
            'version: "1"\nentities:\n  X:\n    tier: 3\n    description: "d"\n'
            "    regex: 'a'\n    validator: ssn\n    generator: g\n",
            "tier 3",
        ),
        (
            'version: "1"\nentities:\n  X:\n    tier: 2\n    description: "d"\n'
            "    validator: ssn\n    generator: g\n",
            "model-carried",
        ),
    ],
    ids=[
        "missing-version",
        "empty-entities",
        "unknown-validator",
        "uncompilable-regex",
        "tier1-without-validator",
        "tier3-with-validator",
        "non-tier3-without-regex",
    ],
)
def test_loader_raises_on_incoherent_config(tmp_path, body, expected):
    with pytest.raises(TaxonomyError, match=expected):
        load_taxonomy(_write(tmp_path, body))


def test_loader_raises_on_missing_file(tmp_path):
    with pytest.raises(TaxonomyError, match="not found"):
        load_taxonomy(tmp_path / "absent.yaml")


def test_loader_checks_generator_names_when_supplied(tmp_path):
    body = (
        'version: "1"\nentities:\n  X:\n    tier: 3\n    description: "d"\n'
        "    generator: not_a_real_generator\n"
    )
    with pytest.raises(TaxonomyError, match="unknown generator"):
        load_taxonomy(_write(tmp_path, body), known_generators={"person_name"})
