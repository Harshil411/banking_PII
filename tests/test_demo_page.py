"""The demo page is served, self-contained, and needs no build step."""

from __future__ import annotations

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
