"""Sensor-health endpoint: derived statuses, coverage contract + fail-closed gates."""

from __future__ import annotations

from collections.abc import Iterator

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from src.api.errors import ArtifactUnreadableError
from src.api.main import app
from src.api.services import lineage_gate, sensor_health
from src.api.services.lineage_gate import ApiLineageResult

_EXPECTED_NOTICES = [
    {
        "key": "quarantine_pending",
        "text": "Quarantine is pending review and not approved.",
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
_ISSUE_TYPE_UNION = {
    "flatline",
    "flatline_zero",
    "variance_collapse",
    "variance_explosion",
    "missingness_spike",
    "abrupt_offset",
    "saturation_low",
    "saturation_high",
    "counter_reset",
    "stale_signal",
    "low_coverage",
}


def _synthetic_frames() -> tuple[pd.DataFrame, dict[str, float]]:
    # Five sensors exercising every §6 status arm, including the
    # quarantine-recommended OR-arm with zero faulty rows.
    summary = pd.DataFrame(
        {
            "sensor": [
                "s_healthy",
                "s_warning",
                "s_faulty",
                "s_quarantine",
                "s_unknown",
            ],
            "n_rows": [100] * 5,
            "n_healthy": [100, 95, 90, 100, 60],
            "n_warning": [0, 5, 0, 0, 0],
            "n_faulty": [0, 0, 10, 0, 0],
            "n_unknown": [0, 0, 0, 0, 40],
            "n_events": [0, 1, 2, 1, 0],
            "issue_row_counts": [
                "{}",
                '{"variance_explosion": 5}',
                '{"flatline_zero": 10}',
                "{}",
                "{}",
            ],
            "quarantine_recommended": [False, False, False, True, False],
        }
    )
    summary["issue_counts"] = summary["issue_row_counts"].map(
        sensor_health._parse_issue_counts
    )
    coverage = {
        "s_healthy": 100.0,
        "s_warning": 99.0,
        "s_faulty": 100.0,
        "s_quarantine": 100.0,
        "s_unknown": 42.0,
    }
    return summary, coverage


@pytest.fixture(autouse=True)
def _synthetic_artifacts(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # Clear before AND after: a leaked cached envelope would silently decouple
    # later tests from their fixtures.
    sensor_health.build_sensor_health_response.cache_clear()
    monkeypatch.setattr(sensor_health, "_load_artifacts", _synthetic_frames)
    yield
    sensor_health.build_sensor_health_response.cache_clear()


def _patch_lineage(monkeypatch: pytest.MonkeyPatch, result: ApiLineageResult) -> None:
    # Fake the startup evaluation so tests never touch real run manifests.
    monkeypatch.setattr(lineage_gate, "evaluate_lineage", lambda: result)


def _lineage(severity: str, *, is_valid: bool = True) -> ApiLineageResult:
    return ApiLineageResult(
        is_valid=is_valid, canonical_match=True, severity=severity, warnings=[]
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("{}", {}), ('{"flatline": 3}', {"flatline": 3})],
)
def test_parse_issue_counts_accepts_json_objects(
    raw: str, expected: dict[str, int]
) -> None:
    assert sensor_health._parse_issue_counts(raw) == expected


@pytest.mark.parametrize("raw", ["not json", "3", "[1, 2]"])
def test_parse_issue_counts_rejects_malformed_cells(raw: str) -> None:
    with pytest.raises(ValueError):
        sensor_health._parse_issue_counts(raw)


@pytest.mark.parametrize("severity", ["ok", "warning"])
def test_sensor_health_returns_200_envelope(
    monkeypatch: pytest.MonkeyPatch, severity: str
) -> None:
    _patch_lineage(monkeypatch, _lineage(severity))
    with TestClient(app) as client:
        resp = client.get("/api/v1/dashboard/sensor-health")
    assert resp.status_code == 200
    assert set(resp.json().keys()) == {"meta", "data"}


def test_sensor_health_meta_matches_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    with TestClient(app) as client:
        meta = client.get("/api/v1/dashboard/sensor-health").json()["meta"]
    assert meta["contractVersion"] == "1.0"
    assert meta["runId"] == "remat-v1-20260616T102558Z"
    assert meta["bomRunId"] == "20260612T124909Z"
    assert meta["dataGeneratedAt"] == "2026-06-16T10:25:58Z"
    # Exact equality locks keys, copy and order (notice presence is contract).
    assert meta["notices"] == _EXPECTED_NOTICES


def test_sensor_health_data_header_and_period(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lineage(monkeypatch, _lineage("warning"))
    with TestClient(app) as client:
        data = client.get("/api/v1/dashboard/sensor-health").json()["data"]
    assert set(data.keys()) == {
        "assetName",
        "datasetName",
        "periodStart",
        "periodEnd",
        "summaryKpis",
        "distribution",
        "problematicSignals",
        "insights",
    }
    assert data["assetName"] == "Pelletizer line"
    assert data["datasetName"] == "Real industrial dataset"
    assert data["periodStart"] == "2024-06-14"
    assert data["periodEnd"] == "2024-10-08"


def test_sensor_health_distribution_matches_status_precedence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    with TestClient(app) as client:
        distribution = client.get("/api/v1/dashboard/sensor-health").json()["data"][
            "distribution"
        ]
    # Locks the §6 precedence (incl. the quarantine OR-arm with n_faulty=0),
    # the fixed status order and that counts sum to the sensor total.
    assert distribution == [
        {"status": "healthy", "label": "Healthy", "count": 1},
        {"status": "warning", "label": "Warning", "count": 1},
        {"status": "critical", "label": "Critical", "count": 2},
        {"status": "unknown", "label": "Unknown", "count": 1},
    ]
    assert sum(item["count"] for item in distribution) == 5


def test_sensor_health_problematic_signals_order_and_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    with TestClient(app) as client:
        signals = client.get("/api/v1/dashboard/sensor-health").json()["data"][
            "problematicSignals"
        ]
    # critical first (more affected rows first), then warning, then unknown;
    # the healthy sensor is excluded.
    assert [s["sensorId"] for s in signals] == [
        "s_faulty",
        "s_quarantine",
        "s_warning",
        "s_unknown",
    ]
    assert [s["status"] for s in signals] == [
        "critical",
        "critical",
        "warning",
        "unknown",
    ]
    # Registry fallback: synthetic ids are not in the curated 17-entry map.
    assert signals[0]["displayName"] == "S faulty"
    assert all(isinstance(s["coveragePct"], int | float) for s in signals)
    assert signals[3]["coveragePct"] == 42.0


def test_sensor_health_issue_types_within_widened_union(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    with TestClient(app) as client:
        signals = client.get("/api/v1/dashboard/sensor-health").json()["data"][
            "problematicSignals"
        ]
    by_id = {s["sensorId"]: s["issueTypes"] for s in signals}
    assert by_id["s_faulty"] == ["flatline_zero"]
    assert by_id["s_quarantine"] == []
    assert by_id["s_warning"] == ["variance_explosion"]
    # Computed low_coverage fires below the threshold (42.0 < 90.0).
    assert by_id["s_unknown"] == ["low_coverage"]
    assert all(
        issue in _ISSUE_TYPE_UNION for issues in by_id.values() for issue in issues
    )


def test_sensor_health_summary_kpis_are_raw_numbers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    with TestClient(app) as client:
        kpis = client.get("/api/v1/dashboard/sensor-health").json()["data"][
            "summaryKpis"
        ]
    assert [k["label"] for k in kpis] == [
        "Healthy signals",
        "Warning signals",
        "Critical signals",
        "Review required",
    ]
    assert [k["value"] for k in kpis] == [1, 1, 2, 4]
    for kpi in kpis:
        assert isinstance(kpi["value"], int)
        assert not isinstance(kpi["value"], str)


def test_sensor_health_insights_and_forbidden_framing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    with TestClient(app) as client:
        resp = client.get("/api/v1/dashboard/sensor-health")
    insights = resp.json()["data"]["insights"]
    assert len(insights) == 3
    for insight in insights:
        assert insight["title"]
        assert insight["body"]
    # §5.3 forbidden-framing tripwire: quarantine is pending, nothing excluded.
    text = resp.text.lower()
    assert "excluded from scoring" not in text
    assert "exclude from automated scoring" not in text
    assert "pending" in text


def test_sensor_health_json_is_camelcase(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    with TestClient(app) as client:
        data = client.get("/api/v1/dashboard/sensor-health").json()["data"]
    assert "summaryKpis" in data and "summary_kpis" not in data
    assert "problematicSignals" in data and "problematic_signals" not in data
    signal = data["problematicSignals"][0]
    assert "sensorId" in signal and "sensor_id" not in signal
    assert "displayName" in signal and "display_name" not in signal
    assert "coveragePct" in signal and "coverage_pct" not in signal
    assert "issueTypes" in signal and "issue_types" not in signal


def test_sensor_health_invalid_lineage_returns_503_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lineage(monkeypatch, _lineage("invalid", is_valid=False))
    with TestClient(app) as client:
        resp = client.get("/api/v1/dashboard/sensor-health")
    assert resp.status_code == 503
    assert resp.json() == _LINEAGE_INVALID_BODY


def test_sensor_health_unreadable_artifacts_return_503_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))

    def _raise() -> tuple[pd.DataFrame, dict[str, float]]:
        raise ArtifactUnreadableError()

    monkeypatch.setattr(sensor_health, "_load_artifacts", _raise)
    with TestClient(app) as client:
        resp = client.get("/api/v1/dashboard/sensor-health")
    assert resp.status_code == 503
    assert resp.json() == _ARTIFACT_UNREADABLE_BODY


def test_sensor_health_response_is_cached_after_first_hit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    calls = {"count": 0}

    def _counting_loader() -> tuple[pd.DataFrame, dict[str, float]]:
        calls["count"] += 1
        return _synthetic_frames()

    monkeypatch.setattr(sensor_health, "_load_artifacts", _counting_loader)
    with TestClient(app) as client:
        first = client.get("/api/v1/dashboard/sensor-health")
        second = client.get("/api/v1/dashboard/sensor-health")
    assert first.status_code == 200
    assert second.status_code == 200
    assert calls["count"] == 1
    assert first.json() == second.json()
