"""Operational timeline endpoint: computed series contract + fail-closed gates."""

from __future__ import annotations

from collections.abc import Iterator

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from src.api.errors import ArtifactUnreadableError
from src.api.main import app
from src.api.services import lineage_gate, timeline
from src.api.services.lineage_gate import ApiLineageResult

_EXPECTED_NOTICES = [
    {
        "key": "read_only",
        "text": "This dashboard is read-only and intended for technical validation.",
    },
    {
        "key": "scores_unchanged",
        "text": "Original anomaly scores are unchanged.",
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

# Five scored days exercising the full §6 status ladder; 2024-01-05 has only
# an unscored row and must be omitted from the series.
_EXPECTED_SERIES = [
    {
        "date": "2024-01-01",
        "deviationScore": 0.48,
        "incidentCount": 1,
        "status": "critical",
    },
    {
        "date": "2024-01-02",
        "deviationScore": 0.2,
        "incidentCount": 1,
        "status": "drift",
    },
    {
        "date": "2024-01-03",
        "deviationScore": 0.3,
        "incidentCount": 1,
        "status": "warning",
    },
    {
        "date": "2024-01-04",
        "deviationScore": 0.95,
        "incidentCount": 0,
        "status": "warning",
    },
    {
        "date": "2024-01-06",
        "deviationScore": 0.1,
        "incidentCount": 1,
        "status": "normal",
    },
]


def _synthetic_frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    scores = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    # 01-01: five rows -> p95 = 0.48 exactly (linear interpolation)
                    "2024-01-01 01:00",
                    "2024-01-01 02:00",
                    "2024-01-01 03:00",
                    "2024-01-01 04:00",
                    "2024-01-01 05:00",
                    "2024-01-02 10:00",
                    "2024-01-03 10:00",
                    "2024-01-04 10:00",  # threshold arm: 0.95 >= 0.9, no overlaps
                    "2024-01-05 10:00",  # unscored-only day -> omitted
                    "2024-01-06 10:00",
                ]
            ),
            "combined_score": [0.1, 0.2, 0.3, 0.4, 0.5, 0.2, 0.3, 0.95, 0.99, 0.1],
            "severity": ["normal"] * 8 + ["unscored", "normal"],
        }
    )
    incidents = pd.DataFrame(
        {
            "incident_id": ["inc-anomaly", "inc-warning", "inc-info", "inc-suppressed"],
            "severity": ["anomaly", "warning", "info", "critical"],
            "start_timestamp": pd.to_datetime(
                [
                    "2024-01-01 06:00",
                    "2024-01-02 00:00",
                    "2024-01-06 00:00",
                    "2024-01-06 00:00",
                ]
            ),
            "end_timestamp": pd.to_datetime(
                [
                    "2024-01-01 20:00",
                    "2024-01-03 23:00",
                    "2024-01-06 12:00",
                    "2024-01-06 23:00",
                ]
            ),
        }
    )
    suppressed = pd.DataFrame({"suppressed_incident_id": ["inc-suppressed"]})
    drift_events = pd.DataFrame(
        {
            "status": ["active", "candidate"],
            "start_timestamp": pd.to_datetime(["2024-01-01 00:00", "2024-01-06 00:00"]),
            "end_timestamp": pd.to_datetime(["2024-01-02 23:59", "2024-01-06 23:00"]),
        }
    )
    unsuppressed = incidents[
        ~incidents["incident_id"].isin(suppressed["suppressed_incident_id"])
    ].reset_index(drop=True)
    return scores, unsuppressed, drift_events


@pytest.fixture(autouse=True)
def _synthetic_artifacts(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # Clear before AND after: a leaked cached envelope would silently decouple
    # later tests from their fixtures.
    timeline.build_timeline_response.cache_clear()
    monkeypatch.setattr(timeline, "_load_artifacts", _synthetic_frames)
    yield
    timeline.build_timeline_response.cache_clear()


def _patch_lineage(monkeypatch: pytest.MonkeyPatch, result: ApiLineageResult) -> None:
    # Fake the startup evaluation so tests never touch real run manifests.
    monkeypatch.setattr(lineage_gate, "evaluate_lineage", lambda: result)


def _lineage(severity: str, *, is_valid: bool = True) -> ApiLineageResult:
    return ApiLineageResult(
        is_valid=is_valid, canonical_match=True, severity=severity, warnings=[]
    )


@pytest.mark.parametrize("severity", ["ok", "warning"])
def test_timeline_returns_200_envelope(
    monkeypatch: pytest.MonkeyPatch, severity: str
) -> None:
    _patch_lineage(monkeypatch, _lineage(severity))
    with TestClient(app) as client:
        resp = client.get("/api/v1/dashboard/timeline")
    assert resp.status_code == 200
    assert set(resp.json().keys()) == {"meta", "data"}


def test_timeline_meta_matches_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    with TestClient(app) as client:
        meta = client.get("/api/v1/dashboard/timeline").json()["meta"]
    assert meta["contractVersion"] == "1.0"
    assert meta["runId"] == "remat-v1-20260616T102558Z"
    assert meta["bomRunId"] == "20260612T124909Z"
    assert meta["dataGeneratedAt"] == "2026-06-16T10:25:58Z"
    # Exact equality locks keys, copy and order (notice presence is contract).
    assert meta["notices"] == _EXPECTED_NOTICES


def test_timeline_data_header_and_period(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_lineage(monkeypatch, _lineage("warning"))
    with TestClient(app) as client:
        data = client.get("/api/v1/dashboard/timeline").json()["data"]
    assert set(data.keys()) == {
        "assetName",
        "datasetName",
        "periodStart",
        "periodEnd",
        "summaryKpis",
        "series",
        "periods",
        "events",
    }
    assert data["assetName"] == "Pelletizer line"
    assert data["datasetName"] == "Real industrial dataset"
    assert data["periodStart"] == "2024-06-14"
    assert data["periodEnd"] == "2024-10-08"


def test_timeline_series_matches_status_ladder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    with TestClient(app) as client:
        series = client.get("/api/v1/dashboard/timeline").json()["data"]["series"]
    # Locks p95 (3 decimals), overlap counts, suppression filtering and the
    # full critical > drift > warning > normal precedence in one comparison.
    assert series == _EXPECTED_SERIES


def test_timeline_omits_days_without_scored_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    with TestClient(app) as client:
        series = client.get("/api/v1/dashboard/timeline").json()["data"]["series"]
    dates = [point["date"] for point in series]
    # 2024-01-05 has one row, but it is unscored-severity -> the day is omitted.
    assert "2024-01-05" not in dates
    assert all(point["deviationScore"] != 0.99 for point in series)


def test_timeline_summary_kpis_are_raw_numbers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    with TestClient(app) as client:
        kpis = client.get("/api/v1/dashboard/timeline").json()["data"]["summaryKpis"]
    assert [k["label"] for k in kpis] == [
        "Analysed days",
        "Incident windows",
        "Sustained drift events",
        "Days with critical evidence",
    ]
    assert [k["value"] for k in kpis] == [5, 3, 1, 1]
    for kpi in kpis:
        assert isinstance(kpi["value"], int)
        assert not isinstance(kpi["value"], str)


def test_timeline_events_include_contract_anchors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    with TestClient(app) as client:
        resp = client.get("/api/v1/dashboard/timeline")
    events = resp.json()["data"]["events"]
    by_date = {event["date"]: event for event in events}
    # Contract-required baseline anchor at the train-window end.
    assert by_date["2024-09-03"]["type"] == "baseline"
    assert by_date["2024-09-17"]["type"] == "review"
    # Peak deviation day computed from the series (first at max, 0.95).
    assert by_date["2024-01-04"]["type"] == "incident"
    assert by_date["2024-01-04"]["severity"] == "warning"
    assert [event["date"] for event in events] == sorted(e["date"] for e in events)
    # §5.3 forbidden-framing tripwire: quarantine is pending, nothing excluded.
    text = resp.text.lower()
    assert "excluded from scoring" not in text
    assert "exclude from automated scoring" not in text
    assert "pending" in text


def test_timeline_periods_fall_back_to_normal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    with TestClient(app) as client:
        periods = client.get("/api/v1/dashboard/timeline").json()["data"]["periods"]
    assert [period["title"] for period in periods] == [
        "Training baseline window",
        "Post-training validation",
        "Sensor fault under review",
    ]
    # Synthetic series days (2024-01-*) fall outside every pinned range.
    assert [period["status"] for period in periods] == ["normal"] * 3
    assert periods[0]["startDate"] == "2024-06-14"
    assert periods[0]["endDate"] == "2024-09-03"


def test_timeline_json_is_camelcase(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    with TestClient(app) as client:
        data = client.get("/api/v1/dashboard/timeline").json()["data"]
    point = data["series"][0]
    assert "deviationScore" in point and "deviation_score" not in point
    assert "incidentCount" in point and "incident_count" not in point
    assert "summaryKpis" in data and "summary_kpis" not in data
    period = data["periods"][0]
    assert "startDate" in period and "start_date" not in period


def test_timeline_invalid_lineage_returns_503_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lineage(monkeypatch, _lineage("invalid", is_valid=False))
    with TestClient(app) as client:
        resp = client.get("/api/v1/dashboard/timeline")
    assert resp.status_code == 503
    assert resp.json() == _LINEAGE_INVALID_BODY


def test_timeline_unreadable_artifacts_return_503_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))

    def _raise() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        raise ArtifactUnreadableError()

    monkeypatch.setattr(timeline, "_load_artifacts", _raise)
    with TestClient(app) as client:
        resp = client.get("/api/v1/dashboard/timeline")
    assert resp.status_code == 503
    assert resp.json() == _ARTIFACT_UNREADABLE_BODY


def test_timeline_response_is_cached_after_first_hit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    calls = {"count": 0}

    def _counting_loader() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        calls["count"] += 1
        return _synthetic_frames()

    monkeypatch.setattr(timeline, "_load_artifacts", _counting_loader)
    with TestClient(app) as client:
        first = client.get("/api/v1/dashboard/timeline")
        second = client.get("/api/v1/dashboard/timeline")
    assert first.status_code == 200
    assert second.status_code == 200
    assert calls["count"] == 1
    assert first.json() == second.json()
