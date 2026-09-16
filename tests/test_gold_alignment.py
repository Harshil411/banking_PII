"""Gold-span integrity for the synthetic corpus.

Every generation run must pass this. An evaluation set whose offsets are
subtly wrong does not look broken -- it looks like a model that mysteriously
underperforms, and it costs days before anyone suspects the data.
"""

from __future__ import annotations

import pytest

from app.core.taxonomy import load_taxonomy
from app.core.types import ValueKind
from synth.generate import (
    HOLDOUT_TEMPLATE_DIR,
    TEMPLATE_DIR,
    generate,
    load_templates,
    write_corpus,
)
from synth.providers import PROVIDERS

from .conftest import TAXONOMY_PATH

CORPUS_SIZE = 500
SEED = 42


@pytest.fixture(scope="module")
def tax():
    return load_taxonomy(TAXONOMY_PATH, known_generators=set(PROVIDERS))


@pytest.fixture(scope="module")
def corpus(tax):
    return generate(SEED, CORPUS_SIZE, tax)


# --------------------------------------------------------------------------
# The invariant the whole evaluation rests on
# --------------------------------------------------------------------------


def test_every_span_slices_back_to_its_own_text(corpus):
    failures = []
    for doc in corpus:
        text = doc["text"]
        for span in doc["spans"]:
            actual = text[span["start"] : span["end"]]
            if actual != span["text"]:
                failures.append(
                    f"{doc['doc_id']} {span['entity_type']}: recorded {span['text']!r} "
                    f"but text[{span['start']}:{span['end']}] is {actual!r}"
                )
    assert not failures, "gold spans disagree with the document:\n  " + "\n  ".join(failures[:10])


def test_search_based_offsets_would_have_been_wrong(corpus):
    """Demonstrates why offsets are recorded during construction.

    A borrower's name appears in the letterhead and again in the body, so
    locating values with str.find after rendering returns the first occurrence
    for every later one. This asserts the corpus actually contains that trap,
    so the test above is guarding something real rather than a hypothetical.
    """
    repeated_value_documents = 0
    for doc in corpus:
        seen: set[str] = set()
        for span in doc["spans"]:
            if span["text"] in seen and doc["text"].find(span["text"]) != span["start"]:
                repeated_value_documents += 1
                break
            seen.add(span["text"])
    assert repeated_value_documents > 0, (
        "no document repeats a value, so this corpus would not expose a find-based bug"
    )


def test_spans_do_not_overlap(corpus):
    for doc in corpus:
        spans = sorted(doc["spans"], key=lambda s: s["start"])
        for earlier, later in zip(spans, spans[1:], strict=False):
            assert earlier["end"] <= later["start"], (
                f"{doc['doc_id']}: {earlier['text']!r} overlaps {later['text']!r}"
            )


def test_spans_are_emitted_in_document_order(corpus):
    for doc in corpus:
        starts = [s["start"] for s in doc["spans"]]
        assert starts == sorted(starts), f"{doc['doc_id']}: spans are not in document order"


def test_spans_are_within_the_document(corpus):
    for doc in corpus:
        length = len(doc["text"])
        for span in doc["spans"]:
            assert 0 <= span["start"] < span["end"] <= length


# --------------------------------------------------------------------------
# Value kinds behave as advertised
# --------------------------------------------------------------------------


def test_valid_spans_pass_their_validators(corpus, tax):
    failures = []
    for doc in corpus:
        for span in doc["spans"]:
            if span["value_kind"] != ValueKind.VALID.value or span["entity_type"] is None:
                continue
            validator = tax.validators.get(span["entity_type"])
            if validator is None:
                continue
            ok, reason = validator(span["text"])
            if not ok:
                failures.append(f"{span['entity_type']} {span['text']!r}: {reason}")
    assert not failures, (
        "valid gold values rejected by their own validators -- recall would collapse:\n  "
        + "\n  ".join(failures[:10])
    )


def test_adversarial_spans_fail_their_validators(corpus, tax):
    """The thesis metric depends on these actually being near-misses."""
    failures = []
    for doc in corpus:
        for span in doc["spans"]:
            if span["value_kind"] != ValueKind.ADVERSARIAL.value:
                continue
            validator = tax.validators[span["entity_type"]]
            if validator(span["text"])[0]:
                failures.append(f"{span['entity_type']} {span['text']!r} was accepted")
    assert not failures, "adversarial values accepted:\n  " + "\n  ".join(failures[:10])


def test_adversarial_spans_still_match_their_scanner(corpus, tax):
    """A near-miss the pattern never matches proves nothing about the validator."""
    failures = []
    for doc in corpus:
        for span in doc["spans"]:
            if span["value_kind"] != ValueKind.ADVERSARIAL.value:
                continue
            scanner = tax.scanners.get(span["entity_type"])
            if scanner is None:
                continue
            window = doc["text"][max(0, span["start"] - 40) : span["end"] + 40]
            if not any(m.group(0) == span["text"] for m in scanner.finditer(window)):
                failures.append(
                    f"{span['entity_type']} {span['text']!r} is not matched by its scanner"
                )
    assert not failures, "\n  ".join(failures[:10])


def test_adversarial_spans_carry_a_reason(corpus):
    for doc in corpus:
        for span in doc["spans"]:
            if span["value_kind"] == ValueKind.ADVERSARIAL.value:
                assert span["note"], f"{span['text']!r} has no explanation of why it is a near-miss"


def test_distractors_belong_to_no_entity_type(corpus):
    for doc in corpus:
        for span in doc["spans"]:
            if span["value_kind"] == ValueKind.DISTRACTOR.value:
                assert span["entity_type"] is None
                assert span["tier"] is None
                assert span["note"]


def test_corpus_contains_all_three_value_kinds(corpus):
    kinds = {s["value_kind"] for doc in corpus for s in doc["spans"]}
    assert kinds == {k.value for k in ValueKind}


def test_every_entity_type_appears(corpus, tax):
    present = {s["entity_type"] for doc in corpus for s in doc["spans"]} - {None}
    missing = set(tax.entities) - present
    assert not missing, f"types absent from the corpus cannot be evaluated: {sorted(missing)}"


def test_adversarial_share_is_material(corpus):
    total = sum(1 for d in corpus for s in d["spans"] if s["entity_type"])
    adversarial = sum(
        1 for d in corpus for s in d["spans"] if s["value_kind"] == ValueKind.ADVERSARIAL.value
    )
    assert 0.02 < adversarial / total < 0.30, f"adversarial share {adversarial / total:.3f}"


# --------------------------------------------------------------------------
# Determinism -- a frozen set must be reproducible from its manifest
# --------------------------------------------------------------------------


def test_same_seed_reproduces_byte_identical_corpus(tmp_path, tax):
    first = write_corpus(generate(SEED, 50, tax), tmp_path / "a", SEED, tax.version, 0.15)
    second = write_corpus(generate(SEED, 50, tax), tmp_path / "b", SEED, tax.version, 0.15)
    assert first["sha256"] == second["sha256"]


def test_different_seed_produces_a_different_corpus(tmp_path, tax):
    first = write_corpus(generate(1, 50, tax), tmp_path / "a", 1, tax.version, 0.15)
    second = write_corpus(generate(2, 50, tax), tmp_path / "b", 2, tax.version, 0.15)
    assert first["sha256"] != second["sha256"]


def test_manifest_records_what_is_needed_to_reproduce(tmp_path, tax):
    manifest = write_corpus(generate(SEED, 20, tax), tmp_path, SEED, tax.version, 0.15)
    required = (
        "seed",
        "taxonomy_version",
        "generator_version",
        "adversarial_rate",
        "n_docs",
        "sha256",
    )
    for key in required:
        assert key in manifest, f"manifest cannot reproduce the corpus without {key}"


# --------------------------------------------------------------------------
# Templates
# --------------------------------------------------------------------------


def test_every_template_is_exercised(corpus):
    used = {doc["template_id"] for doc in corpus}
    assert used == {t.name for t in load_templates()}


def test_every_template_produces_spans(corpus):
    for doc in corpus:
        assert doc["spans"], f"{doc['template_id']} produced a document with no spans"


def test_repeated_slots_reuse_one_value(tax):
    """A borrower named twice in a letter must be the same person."""
    docs = generate(SEED, 60, tax)
    for doc in docs:
        if doc["template_id"] != "loss_mitigation_letter":
            continue
        names = [s["text"] for s in doc["spans"] if s["entity_type"] == "PERSON_NAME"]
        assert names.count(names[0]) >= 2, f"{doc['doc_id']}: borrower name was not reused"
        return
    pytest.fail("no loss_mitigation_letter in the sample")


# --------------------------------------------------------------------------
# Held-out templates
# --------------------------------------------------------------------------


def test_holdout_templates_share_nothing_with_tuning_templates():
    """A held-out template that also appears in the tuning set is not held out."""
    tuning = {t.name for t in load_templates(TEMPLATE_DIR)}
    holdout = {t.name for t in load_templates(HOLDOUT_TEMPLATE_DIR)}
    assert holdout and not tuning & holdout


def test_holdout_corpus_obeys_the_same_invariants(tax):
    documents = generate(7, 80, tax, templates=load_templates(HOLDOUT_TEMPLATE_DIR))
    for doc in documents:
        for span in doc["spans"]:
            assert doc["text"][span["start"] : span["end"]] == span["text"]
            if span["value_kind"] == ValueKind.ADVERSARIAL.value:
                assert not tax.validators[span["entity_type"]](span["text"])[0]
