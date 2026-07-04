"""Dashboard meta endpoint: canonical identity + startup-cached lineage gate."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from src.api.main import app
from src.api.services import lineage_gate
from src.api.services.lineage_gate import ApiLineageResult


def _patch_lineage(monkeypatch: pytest.MonkeyPatch, result: ApiLineageResult) -> None:
    # Fake the startup evaluation so tests never touch real run manifests.
    monkeypatch.setattr(lineage_gate, "evaluate_lineage", lambda: result)


def test_meta_returns_200_and_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_lineage(
        monkeypatch,
        ApiLineageResult(
            is_valid=True,
            canonical_match=True,
            severity="warning",
            warnings=["provenance warning from startup"],
        ),
    )
    with TestClient(app) as client:
        resp = client.get("/api/v1/dashboard/meta")
    assert resp.status_code == 200
    body = resp.json()
    assert body["contractVersion"] == "1.0"
    assert body["runId"] == "remat-v1-20260616T102558Z"
    assert body["bomRunId"] == "20260612T124909Z"
    assert body["dataGeneratedAt"] == "2026-06-16T10:25:58Z"
    assert body["trainWindowEnd"] == "2024-09-03"
    assert isinstance(body["requiredWarnings"], list)


def test_meta_surfaces_startup_lineage(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_lineage(
        monkeypatch,
        ApiLineageResult(
            is_valid=True,
            canonical_match=True,
            severity="warning",
            warnings=["cached at startup"],
        ),
    )
    with TestClient(app) as client:
        lineage = client.get("/api/v1/dashboard/meta").json()["lineage"]
    assert lineage["isValid"] is True
    assert lineage["canonicalMatch"] is True
    assert lineage["severity"] == "warning"
    assert lineage["warnings"] == ["cached at startup"]
    # Not the retired B2.3 hardcoded stub message.
    assert "not yet connected in B2.3" not in " ".join(lineage["warnings"])


def test_meta_returns_200_when_lineage_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    # /meta is the gate banner source: it reports invalid, it does not 503.
    _patch_lineage(
        monkeypatch,
        ApiLineageResult(
            is_valid=False,
            canonical_match=True,
            severity="invalid",
            warnings=["a component run is missing"],
        ),
    )
    with TestClient(app) as client:
        resp = client.get("/api/v1/dashboard/meta")
    assert resp.status_code == 200
    assert resp.json()["lineage"]["severity"] == "invalid"


def test_meta_json_is_camelcase(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_lineage(
        monkeypatch,
        ApiLineageResult(
            is_valid=True, canonical_match=True, severity="ok", warnings=[]
        ),
    )
    with TestClient(app) as client:
        body = client.get("/api/v1/dashboard/meta").json()
    # Lock the casing convention: no snake_case keys leak to the wire.
    assert "runId" in body and "run_id" not in body
    assert (
        "canonicalMatch" in body["lineage"] and "canonical_match" not in body["lineage"]
    )
