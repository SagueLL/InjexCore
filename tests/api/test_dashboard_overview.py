"""Executive overview endpoint: envelope contract + fail-closed lineage gate."""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from src.api.errors import ArtifactUnreadableError
from src.api.main import app
from src.api.services import lineage_gate, sensor_health
from src.api.services.lineage_gate import ApiLineageResult

_EXPECTED_NOTICES = [
    {
        "key": "read_only",
        "text": "This dashboard is read-only and intended for technical validation.",
    },
    {
        "key": "adjusted_interpretive",
        "text": (
            "Adjusted review severity is interpretive post-processing, "
            "not model rescoring."
        ),
    },
    {
        "key": "plant_records_required",
        "text": "Plant records are still required before operational decisions.",
    },
]
_LINEAGE_INVALID_BODY = {
    "error": {
        "code": "LINEAGE_INVALID",
        "message": "Dashboard lineage validation failed.",
    }
}
_ARTIFACT_UNREADABLE_BODY = {
    "error": {
        "code": "ARTIFACT_UNREADABLE",
        "message": "A required artifact could not be read.",
    }
}


@pytest.fixture(autouse=True)
def _synthetic_artifacts(patched_sensor_health: None) -> None:
    # /overview derives "Problematic sensors" through the sensor-health builder's
    # cache, so it now needs that view's synthetic artifacts (conftest). The
    # 5-sensor fixture yields healthy 1 / warning 1 / critical 2 / unknown 1.
    return None


def _patch_lineage(monkeypatch: pytest.MonkeyPatch, result: ApiLineageResult) -> None:
    # Fake the startup evaluation so tests never touch real run manifests.
    monkeypatch.setattr(lineage_gate, "evaluate_lineage", lambda: result)


def _lineage(severity: str, *, is_valid: bool = True) -> ApiLineageResult:
    return ApiLineageResult(
        is_valid=is_valid, canonical_match=True, severity=severity, warnings=[]
    )


@pytest.mark.parametrize("severity", ["ok", "warning"])
def test_overview_returns_200_envelope(
    monkeypatch: pytest.MonkeyPatch, severity: str
) -> None:
    _patch_lineage(monkeypatch, _lineage(severity))
    with TestClient(app) as client:
        resp = client.get("/api/v1/dashboard/overview")
    assert resp.status_code == 200
    assert set(resp.json().keys()) == {"meta", "data"}


def test_overview_meta_matches_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    with TestClient(app) as client:
        meta = client.get("/api/v1/dashboard/overview").json()["meta"]
    assert meta["contractVersion"] == "1.1"
    assert meta["runId"] == "remat-v1-20260616T102558Z"
    assert meta["bomRunId"] == "20260612T124909Z"
    assert meta["dataGeneratedAt"] == "2026-06-16T14:51:48Z"
    # Exact equality locks keys, copy and order (notice presence is contract).
    assert meta["notices"] == _EXPECTED_NOTICES


def test_overview_data_header_and_status(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_lineage(monkeypatch, _lineage("warning"))
    with TestClient(app) as client:
        data = client.get("/api/v1/dashboard/overview").json()["data"]
    assert data["assetName"]
    assert data["datasetName"]
    assert data["periodStart"] == "2024-06-14"
    assert data["periodEnd"] == "2024-10-08"
    assert data["totalRecords"] == 167331
    assert isinstance(data["totalRecords"], int)
    assert data["operationalStatus"] == "warning"
    assert isinstance(data["statusReason"], str)
    assert data["statusReason"]


def test_overview_kpis_are_raw_numbers(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    with TestClient(app) as client:
        kpis = client.get("/api/v1/dashboard/overview").json()["data"]["kpis"]
    assert [k["label"] for k in kpis] == [
        "Analysed records",
        "Detected incidents",
        "Problematic sensors",
        "Contextualised anomalies",
    ]
    # Raw numbers on the wire — never preformatted strings like "167,331".
    # "Problematic sensors" is derived: warning 1 + critical 2 + unknown 1 = 4
    # over the shared 5-sensor fixture. It is never the sensor *total* (5).
    assert [k["value"] for k in kpis] == [167331, 88, 4, 30096]
    for kpi in kpis:
        assert isinstance(kpi["value"], int)
        assert not isinstance(kpi["value"], str)


def test_overview_insights_and_limitations(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    with TestClient(app) as client:
        resp = client.get("/api/v1/dashboard/overview")
    data = resp.json()["data"]
    assert len(data["executiveInsights"]) == 3
    for insight in data["executiveInsights"]:
        assert insight["title"]
        assert insight["body"]
    assert len(data["limitations"]) == 3
    # §5.3 forbidden-framing tripwire: quarantine is pending, nothing excluded.
    text = resp.text.lower()
    assert "excluded from scoring" not in text
    assert "exclude from automated scoring" not in text
    assert "pending" in text


def test_overview_json_is_camelcase(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    with TestClient(app) as client:
        data = client.get("/api/v1/dashboard/overview").json()["data"]
    assert "operationalStatus" in data and "operational_status" not in data
    assert "statusReason" in data and "status_reason" not in data
    assert "executiveInsights" in data and "executive_insights" not in data
    assert "helperText" in data["kpis"][0] and "helper_text" not in data["kpis"][0]
    # Unset optionals are omitted, not null (matches the TS optional fields).
    footerless_insight = data["executiveInsights"][1]
    assert "footer" not in footerless_insight


def test_overview_invalid_lineage_returns_503_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lineage(monkeypatch, _lineage("invalid", is_valid=False))
    with TestClient(app) as client:
        resp = client.get("/api/v1/dashboard/overview")
    assert resp.status_code == 503
    assert resp.json() == _LINEAGE_INVALID_BODY


def test_overview_unreadable_sensor_health_returns_503_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The derived "Problematic sensors" KPI makes /overview fail closed when the
    # sensor-health artifacts are unreadable. Serving a stale pin instead would be
    # the silent fallback the contract forbids.
    _patch_lineage(monkeypatch, _lineage("ok"))

    def _raise() -> tuple[pd.DataFrame, dict[str, float]]:
        raise ArtifactUnreadableError()

    monkeypatch.setattr(sensor_health, "_load_artifacts", _raise)
    with TestClient(app) as client:
        resp = client.get("/api/v1/dashboard/overview")
    assert resp.status_code == 503
    assert resp.json() == _ARTIFACT_UNREADABLE_BODY
