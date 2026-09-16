"""Resolving overlapping, contradictory candidates into one answer.

This is the part of the system with no library underneath it, and it is where
v1 failed: its ``_merge_entities`` merged only spans that already agreed on a
label, so two detectors proposing different labels for the same characters
both survived into the output and then corrupted anonymisation, which replaces
spans by offset.

The rule here is that **evidence class outranks confidence**. Presidio and
most ensembles arbitrate overlapping spans by score. This arbitrates by what
kind of evidence supports the span: a mod-10 proof outranks a 0.99 softmax,
because one is arithmetic and the other is a model's opinion.

Precedence, in order:

1. A tier-1 PASS beats any overlapping candidate.
2. A tier-1 or tier-2 FAIL is removed from contention entirely. It does not
   shadow other candidates on the same characters -- a nine-digit string that
   fails the SSA's rules is not an SSN, but it may still be an account number,
   and suppressing the account-number reading because a stronger type looked
   at the span first would lose a real entity. The failure is still reported
   in ``dropped``, with the arithmetic that rejected it.
3. A tier-2 PASS beats tier 3.
4. Within a tier, the longer span wins. A shorter type nested inside a longer
   one is nearly always an artefact: NMLS_ID's four-to-seven digit pattern
   matches the last seven digits of an EIN, and letting it win would report a
   licence identifier that is really half a tax number.
5. Then a context-gated match beats a generic one. A candidate for a gated
   type is only emitted when a context word was found nearby, so it carries
   evidence a bare pattern match does not: "loan number 0012345678" is a loan
   number, not a deposit account that happens to be ten digits long. This
   ranks below length precisely because of the EIN case above -- gating is
   evidence about which type, not about where the span ends.
6. Then: higher score, taxonomy declaration order, position. The chain must be
   total, because a frozen evaluation set whose diffs shuffle is not a gate.
7. Partial overlaps drop the loser whole. Spans are never truncated: half of
   an account number is not a different, shorter entity.

Tier comes first, and that ordering is measured rather than assumed. Three
arrangements were scored against 300 synthetic servicing documents:

    tier, length, gating, proximity        micro-F1 0.948   (this one)
    length, tier, gating, proximity        micro-F1 0.945
    length, gating, bucketed proximity,    micro-F1 0.936
      then tier

Putting length or proximity ahead of tier lets spaCy's long LOCATION spans
swallow validated ZIPs and states, and lets US_ACCOUNT_NUM claim spans that
belong to narrower types -- its precision fell to 0.526 in the third
arrangement.

The residual cost of tier-first is visible and worth stating: in "credit
account 483920117. SSN 457551275." the account number is labelled SSN,
because SSN is tier 1 and the SSA rules happen to pass. The span is still
redacted, so the privacy outcome is unaffected, but the label is wrong.
US_ACCOUNT_NUM is the weakest non-model type in the taxonomy at F1 0.739, and
this is most of why.
"""

from __future__ import annotations

from dataclasses import replace

from app.core.taxonomy import Taxonomy
from app.core.types import Candidate, Entity, Tier, ValidationStatus

#: Reason recorded when a candidate loses an overlap rather than a validation.
OVERLAP_REASON = "overlapped by a higher-precedence entity: {winner} [tier {tier}] {span}"


def validate(candidate: Candidate, taxonomy: Taxonomy) -> Entity:
    """Run the candidate's validator, if its type has one."""
    spec = taxonomy[candidate.entity_type]
    tier = spec.tier

    if spec.validator is None:
        return Entity.from_candidate(
            candidate,
            tier=tier,
            validation_status=ValidationStatus.NOT_APPLICABLE,
            validator=None,
            reason="no deterministic rule exists for this type",
        )

    ok, reason = taxonomy.validators[candidate.entity_type](candidate.text)
    return Entity.from_candidate(
        candidate,
        tier=tier,
        validation_status=ValidationStatus.PASS if ok else ValidationStatus.FAIL,
        validator=spec.validator,
        reason=reason,
    )


def _contains(outer: Entity, inner: Entity) -> bool:
    """True when ``outer`` strictly contains ``inner``."""
    return (
        outer.start <= inner.start
        and inner.end <= outer.end
        and outer.length > inner.length
    )


def _precedence(entity: Entity, taxonomy: Taxonomy) -> tuple:
    """Total ordering key. Lower sorts better.

    Every component must be included even when it rarely decides anything:
    an incomplete key makes output depend on input order, and the CI gate
    would then diff on noise rather than on regressions.
    """
    return (
        int(entity.tier),
        -entity.length,
        0 if taxonomy[entity.entity_type].is_context_gated else 1,
        entity.context_distance if entity.context_distance is not None else 1 << 30,
        -entity.score,
        taxonomy.order[entity.entity_type],
        entity.start,
        entity.end,
        entity.entity_type,
    )


def _drop_fragments(
    entities: list[Entity], taxonomy: Taxonomy
) -> tuple[list[Entity], list[Entity]]:
    """Remove spans strictly inside a longer, pattern-derived, validated span.

    "10/13/2021" is a well-formed DATE; the "2021" inside it is not separately
    an NMLS identifier, even though NMLS_ID is tier 2 and DATE is tier 3 and
    tier normally decides first. A fragment of a longer pattern match is an
    artefact of the shorter pattern, not independent evidence.

    Restricted to pattern-derived containers on purpose. Model-carried spans
    are not trustworthy as containers -- spaCy routinely returns a LOCATION
    that swallows a following ZIP, and letting those absorb validated entities
    measured worse (micro-F1 0.945 against 0.948).
    """
    containers = [
        e
        for e in entities
        if not taxonomy[e.entity_type].is_model_carried
        and e.validation_status is not ValidationStatus.FAIL
    ]
    kept, fragments = [], []
    for entity in entities:
        swallowed = next(
            (c for c in containers if c is not entity and _contains(c, entity)),
            None,
        )
        if swallowed is None:
            kept.append(entity)
        else:
            fragments.append(
                replace(
                    entity,
                    reason=(
                        f"fragment of a longer {swallowed.entity_type} match "
                        f"{swallowed.text!r}"
                    ),
                )
            )
    return kept, fragments


def _dedupe(entities: list[Entity]) -> list[Entity]:
    """Collapse candidates identical in type and span, keeping the best-scored."""
    best: dict[tuple[str, int, int], Entity] = {}
    for entity in entities:
        key = (entity.entity_type, entity.start, entity.end)
        current = best.get(key)
        if current is None or entity.score > current.score:
            best[key] = entity
    return list(best.values())


def arbitrate(
    candidates: list[Candidate],
    taxonomy: Taxonomy,
) -> tuple[list[Entity], list[Entity]]:
    """Validate, resolve overlaps, and return ``(kept, dropped)``.

    ``kept`` is sorted by position and is guaranteed pairwise non-overlapping,
    which is what makes anonymisation safe. ``dropped`` carries every candidate
    that did not survive, each with the reason -- a failed checksum, or the
    entity that outranked it.
    """
    validated = [validate(candidate, taxonomy) for candidate in candidates]
    validated, fragments = _drop_fragments(validated, taxonomy)

    # Rule 2: validation failures leave contention immediately. They are
    # reported, but they must not shadow a weaker reading of the same span.
    contenders = _dedupe([e for e in validated if e.validation_status is not ValidationStatus.FAIL])
    dropped = [e for e in validated if e.validation_status is ValidationStatus.FAIL] + fragments

    kept: list[Entity] = []
    for entity in sorted(contenders, key=lambda e: _precedence(e, taxonomy)):
        winner = next((k for k in kept if k.overlaps(entity)), None)
        if winner is None:
            kept.append(entity)
            continue
        dropped.append(
            replace(
                entity,
                reason=OVERLAP_REASON.format(
                    winner=winner.entity_type,
                    tier=int(winner.tier),
                    span=f"({winner.start}, {winner.end})",
                ),
            )
        )

    kept.sort(key=lambda e: (e.start, e.end))
    dropped.sort(key=lambda e: (e.start, e.end, e.entity_type))
    return kept, dropped


def counts_by_tier(entities: list[Entity]) -> dict[str, int]:
    counts = {f"tier_{int(tier)}": 0 for tier in Tier}
    for entity in entities:
        counts[f"tier_{int(entity.tier)}"] += 1
    return counts


def counts_by_type(entities: list[Entity]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entity in entities:
        counts[entity.entity_type] = counts.get(entity.entity_type, 0) + 1
    return dict(sorted(counts.items()))
