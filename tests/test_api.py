"""HTTP surface."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

SAMPLE = (
    "RE: Loan Number 0012345678. Borrower verified with SSN 457551275. "
    "Wire to routing number 011000015. Contact (415) 555-0142 or "
    "a.borrower@example.com about $1,204.55 due 03/15/2024."
)


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(Settings(detector="deterministic"))) as test_client:
        yield test_client


# --------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------


def test_detect_returns_entities_and_rejections(client):
    body = client.post("/v1/detect", json={"text": SAMPLE}).json()
    labels = {e["entity_type"] for e in body["entities"]}
    assert {"SSN", "ABA_ROUTING", "PHONE", "EMAIL", "MONEY", "DATE"} <= labels
    assert all(e["reason"] for e in body["dropped"])


def test_detect_reports_the_evidence_for_each_entity(client):
    body = client.post("/v1/detect", json={"text": "Wire routing number 011000015."}).json()
    entity = next(e for e in body["entities"] if e["entity_type"] == "ABA_ROUTING")
    assert entity["tier"] == 1
    assert entity["validation_status"] == "pass"
    assert entity["validator"] == "aba_routing"
    assert "checksum" in entity["reason"]


def test_tier_three_entities_are_not_applicable_never_pass(client):
    body = client.post("/v1/detect", json={"text": "Property at 88 Oak Street."}).json()
    entity = next(e for e in body["entities"] if e["entity_type"] == "STREET_ADDRESS")
    assert entity["validation_status"] == "not_applicable"
    assert entity["validator"] is None


def test_response_carries_version_engine_and_timings(client):
    body = client.post("/v1/detect", json={"text": SAMPLE}).json()
    assert body["taxonomy_version"] == "1.0.0"
    assert body["engine"]["name"] == "deterministic"
    assert body["request_id"]
    assert {"detect", "arbitrate", "total"} <= set(body["timing_ms"])
    assert 0.0 <= body["rejection_rate"] <= 1.0


def test_offsets_index_the_submitted_text(client):
    body = client.post("/v1/detect", json={"text": SAMPLE}).json()
    for entity in body["entities"]:
        assert SAMPLE[entity["start"] : entity["end"]] == entity["text"]


def test_entity_type_filter(client):
    body = client.post("/v1/detect", json={"text": SAMPLE, "entity_types": ["SSN"]}).json()
    assert {e["entity_type"] for e in body["entities"]} <= {"SSN"}


def test_unknown_entity_type_is_rejected(client):
    response = client.post("/v1/detect", json={"text": "x", "entity_types": ["NOT_A_TYPE"]})
    assert response.status_code == 422
    assert "NOT_A_TYPE" in response.json()["detail"]


def test_oversized_text_is_refused(client):
    response = client.post("/v1/detect", json={"text": "x" * 300_000})
    assert response.status_code == 413


def test_unknown_fields_are_rejected(client):
    assert client.post("/v1/detect", json={"text": "x", "nope": 1}).status_code == 422


def test_empty_text_is_valid_and_finds_nothing(client):
    body = client.post("/v1/detect", json={"text": ""}).json()
    assert body["entities"] == []


# --------------------------------------------------------------------------
# Anonymisation
# --------------------------------------------------------------------------


def test_anonymize_removes_every_reported_entity(client):
    body = client.post("/v1/anonymize", json={"text": SAMPLE}).json()
    for entity in body["entities"]:
        assert entity["text"] not in body["redacted"]


def test_anonymize_leaves_a_proven_non_ssn_in_place(client):
    """The default: a span a validator proved invalid is not redacted.

    Note the "SSN" in the text. SSN is context-gated, so without a context
    word nearby it is never even a candidate and there is nothing to reject --
    which is a different outcome reached for a different reason.
    """
    text = "Taxpayer SSN 666121234 in the file."
    body = client.post("/v1/anonymize", json={"text": text}).json()
    assert body["redacted"] == text
    assert any(e["entity_type"] == "SSN" for e in body["dropped"])


def test_anonymize_can_redact_failed_tier_one_on_request(client):
    text = "Taxpayer SSN 666121234 in the file."
    body = client.post(
        "/v1/anonymize", json={"text": text, "redact_failed_tier1": True}
    ).json()
    assert "666121234" not in body["redacted"]


def test_redacting_failed_tier_one_survives_a_competing_reading(client):
    """Was HTTP 500: the failed SSN and the account number claim the same digits."""
    text = "Taxpayer SSN, credit to account 666121234 today."
    response = client.post("/v1/anonymize", json={"text": text, "redact_failed_tier1": True})
    assert response.status_code == 200
    assert "666121234" not in response.json()["redacted"]


def test_the_policy_flag_does_not_leak_between_requests(client):
    """A per-request policy must not mutate the shared pipeline."""
    text = "Taxpayer SSN 666121234 in the file."
    client.post("/v1/anonymize", json={"text": text, "redact_failed_tier1": True})
    body = client.post("/v1/anonymize", json={"text": text}).json()
    assert body["redacted"] == text


# --------------------------------------------------------------------------
# Taxonomy and operations
# --------------------------------------------------------------------------


def test_taxonomy_endpoint_describes_every_type(client):
    body = client.get("/v1/taxonomy").json()
    assert body["version"] == "1.0.0"
    assert len(body["entities"]) == 19
    assert {e["tier"] for e in body["entities"]} == {1, 2, 3}
    assert all(e["description"] for e in body["entities"])


def test_healthz_does_not_depend_on_the_model(client):
    """Liveness must answer while loading, or an orchestrator restarts a warming pod."""
    response = TestClient(create_app(Settings(detector="deterministic"))).get("/healthz")
    assert response.status_code == 200 and response.json()["status"] == "ok"


def test_readyz_reports_the_loaded_configuration(client):
    body = client.get("/readyz").json()
    assert body["status"] == "ready"
    assert body["taxonomy_version"] == "1.0.0"
    assert body["engine"] == "deterministic"


def test_readyz_fails_when_startup_failed(tmp_path):
    """A broken deployment must not look like a service that finds no entities."""
    app = create_app(Settings(taxonomy_path=tmp_path / "missing.yaml"))
    with TestClient(app, raise_server_exceptions=False) as broken:
        response = broken.get("/readyz")
        assert response.status_code == 503
        assert "not found" in response.json()["detail"]
        assert broken.get("/healthz").status_code == 200


def test_openapi_schema_is_generated(client):
    schema = client.get("/openapi.json").json()
    assert "/v1/detect" in schema["paths"]
    assert "/v1/anonymize" in schema["paths"]
