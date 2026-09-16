"""Shared fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.taxonomy import Taxonomy, load_taxonomy

REPO_ROOT = Path(__file__).resolve().parents[1]
TAXONOMY_PATH = REPO_ROOT / "taxonomy" / "entities.yaml"
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def taxonomy() -> Taxonomy:
    return load_taxonomy(TAXONOMY_PATH)


@pytest.fixture(scope="session")
def vectors() -> dict:
    """Externally sourced validator test vectors.

    See the ``_provenance`` key in the file: these values come from published
    third-party sources, not from this project's generator, so a shared
    misreading of a specification cannot hide in both.
    """
    return json.loads((FIXTURES / "external_vectors.json").read_text(encoding="utf-8"))
