"""Dashboard meta endpoint: canonical identity + lineage-gate shape, camelCase JSON."""

from __future__ import annotations

from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)


def test_meta_returns_200() -> None:
    assert client.get("/api/v1/dashboard/meta").status_code == 200


def test_meta_payload_matches_contract() -> None:
    body = client.get("/api/v1/dashboard/meta").json()
    assert body["contractVersion"] == "1.0"
    assert body["runId"] == "remat-v1-20260616T102558Z"
    assert body["bomRunId"] == "20260612T124909Z"
    assert body["dataGeneratedAt"] == "2026-06-16T10:25:58Z"
    assert body["trainWindowEnd"] == "2024-09-03"
    assert body["lineage"]["isValid"] is True
    assert body["lineage"]["canonicalMatch"] is True
    assert body["lineage"]["severity"] == "warning"
    assert isinstance(body["requiredWarnings"], list)


def test_meta_json_is_camelcase() -> None:
    body = client.get("/api/v1/dashboard/meta").json()
    # Lock the casing convention: no snake_case keys leak to the wire.
    assert "runId" in body and "run_id" not in body
    assert "canonicalMatch" in body["lineage"]
