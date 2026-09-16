"""The demo page: served, self-contained, strictly sandboxed, and offset-faithful."""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import STATIC_DIR, create_app

ASSETS = STATIC_DIR / "assets"
HTML = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
JS = (ASSETS / "app.js").read_text(encoding="utf-8")
CSS = (ASSETS / "app.css").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(Settings(detector="deterministic"))) as test_client:
        yield test_client


# --------------------------------------------------------------------------
# Serving
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/assets/app.css",
        "/assets/app.js",
        "/assets/theme.js",
        "/assets/samples.json",
        "/assets/favicon.svg",
        "/assets/fonts/plex-sans-var.woff2",
        "/assets/fonts/jetbrains-mono-var.woff2",
    ],
)
def test_assets_are_served(client, path):
    assert client.get(path).status_code == 200


def test_font_licences_ship_with_the_fonts():
    """Both faces are SIL OFL 1.1, which permits redistribution with the licence."""
    for name in ("OFL-IBM-Plex.txt", "OFL-JetBrains-Mono.txt"):
        assert "Open Font License" in (ASSETS / "fonts" / name).read_text(encoding="utf-8")


def test_samples_each_show_a_proof_and_a_rejection(client):
    """A sample that rejects nothing opens the page on "0 rejected" and proves nothing."""
    samples = client.get("/assets/samples.json").json()
    assert len(samples) >= 4
    assert any(s["split"] == "held_out" for s in samples)
    with TestClient(create_app(Settings(detector="presidio"))) as full:
        for sample in samples:
            body = full.post("/v1/detect", json={"text": sample["text"]}).json()
            assert any(e["tier"] == 1 for e in body["entities"]), sample["label"]
            assert any(d["validation_status"] == "fail" for d in body["dropped"]), sample["label"]


# --------------------------------------------------------------------------
# Sandboxing
# --------------------------------------------------------------------------


def test_page_loads_nothing_from_a_third_party_host():
    """No CDN, no web fonts. The demo must work behind a restrictive network."""
    for source in (HTML, CSS):
        assert not re.findall(r'(?:src|href|url)\s*[=(]\s*["\']?https?://(?!github\.com)', source)


def test_no_inline_script_or_style():
    """The CSP forbids both, so either would silently break the page."""
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", HTML), "inline <script> found"
    assert "<style" not in HTML
    assert not re.search(r'\sstyle\s*=\s*["\']', HTML), "inline style attribute found"
    assert "innerHTML" not in JS, "user text must never be parsed as HTML"


def test_security_headers(client):
    page = client.get("/")
    csp = page.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "'unsafe-inline'" not in csp
    assert page.headers["x-content-type-options"] == "nosniff"


def test_detection_responses_are_never_cached(client):
    """They echo the submitted document, which is PII."""
    for path in ("/v1/detect", "/v1/anonymize"):
        assert (
            client.post(path, json={"text": "SSN 457551275"}).headers["cache-control"] == "no-store"
        )


def test_swagger_docs_are_not_blanked_by_the_csp(client):
    """/docs loads Swagger UI from a CDN, so it is exempt from the strict policy."""
    assert "content-security-policy" not in client.get("/docs").headers


def test_frame_ancestors_is_configurable():
    app = create_app(
        Settings(detector="deterministic", frame_ancestors="https://portfolio.example")
    )
    with TestClient(app) as test_client:
        csp = test_client.get("/").headers["content-security-policy"]
    assert "frame-ancestors https://portfolio.example" in csp


# --------------------------------------------------------------------------
# Evaluation endpoint
# --------------------------------------------------------------------------


def test_evaluation_serves_the_committed_baseline(client):
    body = client.get("/v1/evaluation").json()
    assert set(body["splits"]) == {"in_distribution", "held_out"}
    assert 0 < body["splits"]["held_out"]["strict"]["micro"]["f1"] <= 1


def test_evaluation_is_optional(tmp_path):
    app = create_app(Settings(detector="deterministic", evaluation_path=tmp_path / "absent.json"))
    with TestClient(app) as test_client:
        assert test_client.get("/v1/evaluation").status_code == 404
        assert test_client.get("/readyz").status_code == 200


# --------------------------------------------------------------------------
# Accessibility contracts that are cheap to assert statically
# --------------------------------------------------------------------------


def test_theme_aware_and_motion_aware():
    assert "prefers-color-scheme" in CSS
    assert "prefers-reduced-motion" in CSS


def test_tier_is_not_conveyed_by_colour_alone():
    """Each tier gets a distinct underline pattern, not just a hue."""
    for pattern in ("solid", "dashed", "dotted", "line-through"):
        assert pattern in CSS


def test_textarea_has_a_visible_label():
    assert re.search(r'<label[^>]+for="text"', HTML)


# --------------------------------------------------------------------------
# The offset walk
# --------------------------------------------------------------------------


def _segments(text: str, entities: list[dict], dropped: list[dict]) -> list[dict]:
    """Transliteration of segments() in assets/app.js.

    There is no JavaScript runtime in this project's toolchain, so the page's
    offset walk is checked by reimplementing it. A deliberate duplicate that can
    drift from the original; it exists because the failure it guards against --
    marks at the wrong offsets, or a document that does not survive the round
    trip -- is silent and disfiguring.
    """

    def overlaps(a, b):
        return a["start"] < b["end"] and b["start"] < a["end"]

    kept = sorted(entities, key=lambda e: (e["start"], e["end"]))
    failed = sorted(
        (
            d
            for d in dropped
            if d["validation_status"] == "fail" and not any(overlaps(k, d) for k in kept)
        ),
        key=lambda d: (d["start"], d["tier"]),
    )
    marks = [{"primary": e, "rejected": False} for e in kept]
    for candidate in failed:
        if not any(m["rejected"] and overlaps(m["primary"], candidate) for m in marks):
            marks.append({"primary": candidate, "rejected": True})
    marks.sort(key=lambda m: m["primary"]["start"])

    runs, cursor = [], 0
    for mark in marks:
        start, end = mark["primary"]["start"], mark["primary"]["end"]
        if start < cursor:
            continue
        if start > cursor:
            runs.append({"text": text[cursor:start]})
        runs.append({"text": text[start:end], "mark": mark})
        cursor = end
    if cursor < len(text):
        runs.append({"text": text[cursor:]})
    return runs


def test_js_still_exports_the_function_being_transliterated():
    assert "export function segments(text, entities, dropped)" in JS


def test_segments_reproduce_every_sample_exactly(client):
    for sample in client.get("/assets/samples.json").json():
        body = client.post("/v1/detect", json={"text": sample["text"]}).json()
        runs = _segments(sample["text"], body["entities"], body["dropped"])
        assert "".join(r["text"] for r in runs) == sample["text"], sample["label"]
        assert sum(1 for r in runs if "mark" in r and not r["mark"]["rejected"]) == len(
            body["entities"]
        )


def test_rejected_near_miss_is_drawn_when_nothing_else_claims_it(client):
    text = "Loan MIN 100002300000000019 was referenced."
    body = client.post("/v1/detect", json={"text": text}).json()
    rejected = [
        r
        for r in _segments(text, body["entities"], body["dropped"])
        if r.get("mark", {}).get("rejected")
    ]
    assert [r["text"] for r in rejected] == ["100002300000000019"]


def test_a_rejection_under_a_kept_entity_is_not_drawn_twice(client):
    """A failed SSN reading of a kept routing number stays in the table, not in the text."""
    text = "Wire to routing number 011000015 today."
    body = client.post("/v1/detect", json={"text": text}).json()
    runs = _segments(text, body["entities"], body["dropped"])
    assert [r["text"] for r in runs if "mark" in r] == ["011000015"]
    assert not any(r["mark"]["rejected"] for r in runs if "mark" in r)


def test_distractors_are_left_unmarked(client):
    text = "The note rate of 6.875% has not changed since origination."
    body = client.post("/v1/detect", json={"text": text}).json()
    assert not [r for r in _segments(text, body["entities"], body["dropped"]) if "mark" in r]


def test_json_is_valid():
    json.loads((ASSETS / "samples.json").read_text(encoding="utf-8"))
