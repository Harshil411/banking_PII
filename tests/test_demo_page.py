"""The demo page is served, self-contained, and needs no build step."""

from __future__ import annotations

import html
import json
import re

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import STATIC_DIR, create_app


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(Settings(detector="deterministic"))) as test_client:
        yield test_client


def test_page_is_served_at_the_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Mortgage PII Service" in response.text


def test_samples_are_served_and_parse(client):
    response = client.get("/samples.js")
    assert response.status_code == 200
    payload = json.loads(response.text.split("= ", 1)[1].rstrip(";\n"))
    assert len(payload) >= 3
    assert all(item["label"] and len(item["text"]) > 200 for item in payload)


def test_page_loads_nothing_from_a_third_party_host():
    """No CDN, no web fonts. The demo must work behind a restrictive network."""
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    external = re.findall(r'(?:src|href)\s*=\s*["\'](https?:)?//[^"\']+', html)
    assert not external, f"external resources would break an offline demo: {external}"


def test_page_polls_readyz_so_a_cold_start_looks_intentional():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    assert "/readyz" in html
    assert "cold start" in html.lower()


def test_page_renders_from_offsets_not_by_rematching():
    """Re-finding values client side would disagree with the server's spans."""
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    assert "e.start" in html and "e.end" in html


def test_page_is_theme_aware():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    assert "prefers-color-scheme" in html


def _highlight(text: str, entities: list[dict]) -> str:
    """Transliteration of highlight() in index.html.

    There is no JavaScript runtime in this project's toolchain, so the page's
    offset walk is checked by reimplementing it here. This is a deliberate
    duplicate and can drift from the original; it exists because the failure it
    guards against -- marks landing at the wrong offsets, or the document not
    surviving the round trip -- is silent and disfiguring.
    """
    out, cursor = [], 0
    for entity in sorted(entities, key=lambda e: e["start"]):
        if entity["start"] < cursor:
            continue
        out.append(html.escape(text[cursor : entity["start"]]))
        marked = html.escape(text[entity["start"] : entity["end"]])
        out.append(f'<mark data-tier="{entity["tier"]}">{marked}</mark>')
        cursor = entity["end"]
    out.append(html.escape(text[cursor:]))
    return "".join(out)


def test_highlighting_preserves_the_document_exactly(client):
    """Stripping the markup must return the original text, byte for byte."""
    payload = json.loads(client.get("/samples.js").text.split("= ", 1)[1].rstrip(";\n"))
    for sample in payload:
        text = sample["text"]
        body = client.post("/v1/detect", json={"text": text}).json()
        rendered = _highlight(text, body["entities"])
        stripped = html.unescape(re.sub(r"<[^>]+>", "", rendered))
        assert stripped == text, f"{sample['label']}: highlighting altered the document"
        assert rendered.count("<mark") == len(body["entities"])


def test_highlighting_marks_the_right_characters(client):
    text = "Wire to routing number 011000015 today."
    body = client.post("/v1/detect", json={"text": text}).json()
    rendered = _highlight(text, body["entities"])
    assert '<mark data-tier="1">011000015</mark>' in rendered


def test_highlighting_leaves_distractors_unmarked(client):
    """An interest rate is PII-shaped and must not be marked."""
    text = "The note rate of 6.875% has not changed since origination."
    body = client.post("/v1/detect", json={"text": text}).json()
    assert not any(e["text"] == "6.875%" for e in body["entities"])
    assert "<mark" not in _highlight(text, body["entities"])
