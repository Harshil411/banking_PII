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

#: Start of the reason recorded for a fragment of a longer match. A fragment is
#: an artefact of a shorter pattern, not a reading of the document, so
#: consumers that count readings -- the rejection rate -- leave it out.
FRAGMENT_REASON = "fragment of a longer "


#: Start of the reason recorded for a passing fragment dropped along with a
#: container that lost an overlap. It never contended, so it was not outranked.
ORPHAN_REASON = "inside a longer "


def is_fragment(entity: Entity) -> bool:
    return entity.reason is not None and entity.reason.startswith(FRAGMENT_REASON)


def is_rejection(entity: Entity) -> bool:
    """A reading a validator rejected in its own right -- not an artefact of a longer match."""
    return entity.validation_status is ValidationStatus.FAIL and not is_fragment(entity)


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


def _is_container(entity: Entity, taxonomy: Taxonomy) -> bool:
    """Pattern-derived and not failed: evidence that its characters form one value.

    Model-carried spans are not trustworthy as containers -- spaCy routinely
    returns a LOCATION that swallows a following ZIP, and letting those absorb
    validated entities measured worse (micro-F1 0.945 against 0.948).
    """
    return (
        not taxonomy[entity.entity_type].is_model_carried
        and entity.validation_status is not ValidationStatus.FAIL
    )


def _drop_fragments(
    entities: list[Entity], taxonomy: Taxonomy
) -> tuple[list[Entity], list[Entity]]:
    """Set aside spans strictly inside a longer, pattern-derived, validated span.

    "10/13/2021" is a well-formed DATE; the "2021" inside it is not separately
    an NMLS identifier, even though NMLS_ID is tier 2 and DATE is tier 3 and
    tier normally decides first. A fragment of a longer pattern match is an
    artefact of the shorter pattern, not independent evidence.

    How each fragment is reported is decided after ranking, in ``arbitrate``:
    a container can still lose an overlap.
    """
    containers = [e for e in entities if _is_container(e, taxonomy)]
    kept, fragments = [], []
    for entity in entities:
        if any(_contains(c, entity) for c in containers):
            fragments.append(entity)
        else:
            kept.append(entity)
    return kept, fragments


def _dedupe(entities: list[Entity], taxonomy: Taxonomy) -> list[Entity]:
    """Collapse readings identical in type and span to one.

    The survivor is the best by the same total ordering arbitration uses, then
    by source, pattern and reason, so it never depends on the order detectors
    ran in -- not
    even when two readings tie on score but differ in context distance, which
    is itself a precedence component. An incomplete key is how
    order-dependence gets in.
    """
    best: dict[tuple[str, int, int], tuple[tuple, Entity]] = {}
    for entity in entities:
        span = (entity.entity_type, entity.start, entity.end)
        rank = (
            _precedence(entity, taxonomy),
            entity.source,
            entity.pattern_name or "",
            entity.reason or "",
        )
        if span not in best or rank < best[span][0]:
            best[span] = (rank, entity)
    return [entity for _, entity in best.values()]


def arbitrate(
    candidates: list[Candidate],
    taxonomy: Taxonomy,
) -> tuple[list[Entity], list[Entity]]:
    """Validate, resolve overlaps, and return ``(kept, dropped)``.

    ``kept`` is sorted by position and is guaranteed pairwise non-overlapping,
    which is what makes anonymisation safe. ``dropped`` carries every distinct
    reading that did not survive -- one entry per type and span, however many
    detectors proposed it -- each with the reason: a failed check, the entity
    that outranked it, or the longer match it was a fragment of.
    """
    validated = [validate(candidate, taxonomy) for candidate in candidates]
    validated, fragments = _drop_fragments(validated, taxonomy)

    # Rule 2: validation failures leave contention immediately. They are
    # reported, but they must not shadow a weaker reading of the same span.
    contenders = _dedupe(
        [e for e in validated if e.validation_status is not ValidationStatus.FAIL], taxonomy
    )
    failures = [e for e in validated if e.validation_status is ValidationStatus.FAIL]

    kept: list[Entity] = []
    dropped: list[Entity] = []
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

    # How a fragment is *reported* depends on what was kept; whether it is
    # kept does not -- fragments never contend.
    #
    # If a kept container strictly contains it, its characters belong to that
    # validated value and it is an artefact, named after it. Kept entities
    # never overlap, so there is at most one, and the reason cannot depend on
    # detector order. Model-carried spans do not count, here as anywhere else
    # a container is meant: otherwise a failed SSN's classification would
    # depend on whether an unrelated address candidate had happened to exist.
    #
    # Otherwise nothing kept vouches for its characters. A failed one is then
    # a rejection in its own right: reported as a fragment, a failed SSN
    # inside an address that lost to an EIN was neither counted in the
    # rejection rate nor redacted by the over-redact policy.
    #
    # A *passing* one is still dropped, and its characters reach the output.
    # That predates this rule and is recorded in DECISIONS.md: letting it
    # contend after the first pass broke precedence (a tier-1 orphan lost to a
    # tier-3 winner it outranks), and a correct rule needs fragments resolved
    # inside the single ranked pass. It is not an artefact, so it is reported
    # without the fragment marker and counts as the validated reading it is.
    artefacts: list[Entity] = []
    for fragment in fragments:
        cover = next(
            (k for k in kept if _is_container(k, taxonomy) and _contains(k, fragment)), None
        )
        if cover is not None:
            reason = f"{FRAGMENT_REASON}{cover.entity_type} match {cover.text!r}"
            # Keep the arithmetic: rule 2 promises a failure is reported with
            # what rejected it, and a fragment's failure is still evidence.
            if fragment.validation_status is ValidationStatus.FAIL and fragment.reason:
                reason += f"; on its own it fails: {fragment.reason}"
            artefacts.append(replace(fragment, reason=reason))
        elif fragment.validation_status is ValidationStatus.FAIL:
            failures.append(fragment)
        else:
            # Named after a container that contended and lost -- never one that
            # was itself a fragment, which did not contend. The outermost
            # container of any nesting is one, so this is never empty.
            holder = min(
                (c for c in validated if _is_container(c, taxonomy) and _contains(c, fragment)),
                key=lambda c: _precedence(c, taxonomy),
            )
            artefacts.append(
                replace(
                    fragment,
                    reason=(
                        f"{ORPHAN_REASON}{holder.entity_type} match {holder.text!r}, which "
                        "lost an overlap; dropped with it"
                    ),
                )
            )

    # Failures and fragments are deduplicated as contenders are: two detectors
    # proposing the same failed reading is one rejection, and every consumer
    # of ``dropped`` -- the demo's counts, the rejection rate -- would
    # otherwise count it twice, in an order that depended on which ran first.
    dropped += _dedupe(failures, taxonomy) + _dedupe(artefacts, taxonomy)

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
