"""Drift & Anomaly endpoint: evidence funnel contract + fail-closed gates."""

from __future__ import annotations

from collections.abc import Iterator

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from src.api.errors import ArtifactUnreadableError
from src.api.main import app
from src.api.services import drift_anomaly, lineage_gate
from src.api.services.drift_anomaly import _Artifacts
from src.api.services.lineage_gate import ApiLineageResult

_EXPECTED_NOTICES = [
    {
        "key": "healthy_only_proxy",
        "text": "Healthy-only residual drift is a proxy view.",
    },
    {
        "key": "scores_unchanged",
        "text": "Original anomaly scores are unchanged.",
    },
    {
        "key": "adjusted_interpretive",
        "text": (
            "Adjusted review severity is interpretive post-processing, "
            "not model rescoring."
        ),
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

# Five scored days exercising the full §6 ladder mapped into this view's
# severity vocabulary (drift-status days read as warning — no drift slot);
# 2024-01-05 has only an unscored row and must be omitted from the series.
_EXPECTED_SERIES = [
    {
        "date": "2024-01-01",
        "anomalyScore": 0.48,
        "anomalyCount": 3,
        "residualCount": 2,
        "severity": "critical",
    },
    {
        "date": "2024-01-02",
        "anomalyScore": 0.2,
        "anomalyCount": 1,
        "residualCount": 1,
        "severity": "warning",  # drift-event day -> warning (mapped, locked)
    },
    {
        "date": "2024-01-03",
        "anomalyScore": 0.3,
        "anomalyCount": 1,
        "residualCount": 0,
        "severity": "warning",
    },
    {
        "date": "2024-01-04",
        "anomalyScore": 0.95,
        "anomalyCount": 0,
        "residualCount": 0,
        "severity": "warning",  # threshold arm: p95 >= 0.9, no overlaps
    },
    {
        "date": "2024-01-06",
        "anomalyScore": 0.1,
        "anomalyCount": 0,
        "residualCount": 0,
        "severity": "normal",
    },
]

_QUARANTINE_SCENARIO = "quarantine_inlet_hopper_points_interpretive"


def _synthetic_artifacts_frames() -> _Artifacts:
    scores = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    # 01-01: five rows -> p95 = 0.48 exactly; 3 non-normal.
                    "2024-01-01 01:00",
                    "2024-01-01 02:00",
                    "2024-01-01 03:00",
                    "2024-01-01 04:00",
                    "2024-01-01 05:00",
                    "2024-01-02 10:00",
                    "2024-01-03 10:00",
                    "2024-01-04 10:00",  # threshold arm: 0.95 >= 0.9
                    "2024-01-05 10:00",  # unscored-only day -> omitted
                    "2024-01-06 10:00",
                ]
            ),
            "combined_score": [0.1, 0.2, 0.3, 0.4, 0.5, 0.2, 0.3, 0.95, 0.99, 0.1],
            "severity": [
                "normal",
                "normal",
                "warning",
                "anomaly",
                "anomaly",
                "warning",
                "anomaly",
                "normal",
                "unscored",
                "normal",
            ],
            # Trigger tokens on normal rows (first) and empty strings (last)
            # must never count toward per-detector evidence.
            "triggered_detectors": [
                "statistical",
                None,
                "statistical|pca_q",
                "statistical|pca_q|pca_t2",
                "mahalanobis|isolation_forest",
                "pca_q",
                "statistical|pca_t2",
                None,
                None,
                "",
            ],
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
    unsuppressed = incidents[
        ~incidents["incident_id"].isin(suppressed["suppressed_incident_id"])
    ].reset_index(drop=True)
    drift_events = pd.DataFrame(
        {
            "status": ["active", "candidate"],
            "start_timestamp": pd.to_datetime(["2024-01-01 00:00", "2024-01-06 00:00"]),
            "end_timestamp": pd.to_datetime(["2024-01-02 23:59", "2024-01-06 23:00"]),
        }
    )
    scenario_scores = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2024-01-01 01:00",  # quarantine, unsuppressed -> counts
                    "2024-01-01 02:00",  # quarantine, unsuppressed -> counts
                    "2024-01-01 03:00",  # quarantine, suppressed -> excluded
                    "2024-01-01 01:00",  # baseline scenario -> excluded
                    "2024-01-02 12:00",  # quarantine, unsuppressed -> counts
                    "2024-01-07 09:00",  # day without scored rows -> dropped
                ]
            ),
            "scenario_id": [
                _QUARANTINE_SCENARIO,
                _QUARANTINE_SCENARIO,
                _QUARANTINE_SCENARIO,
                "baseline_v1",
                _QUARANTINE_SCENARIO,
                _QUARANTINE_SCENARIO,
            ],
            "row_suppressed_for_review": [False, False, True, False, False, False],
        }
    )
    rate = pd.DataFrame(
        {
            "scenario_id": ["baseline_v1", _QUARANTINE_SCENARIO],
            "original_warning_count": [2, 2],
            "original_anomaly_count": [5, 5],
            "suppressed_count": [0, 4],
            "remaining_warning_count": [2, 2],
            "remaining_anomaly_count": [5, 1],
            "healthy_only_residual_count": [0, 9],
            "top_remaining_sensors": [
                "inlet_hopper_points:5|inlet_hopper_humidity:2",
                "inlet_hopper_points:4|inlet_hopper_humidity:3"
                "|feeder_hopper_temp:2|granulator_power:1",
            ],
        }
    )
    return _Artifacts(scores, unsuppressed, drift_events, scenario_scores, rate.iloc[1])


@pytest.fixture(autouse=True)
def _synthetic_artifacts(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # Clear before AND after: a leaked cached envelope would silently decouple
    # later tests from their fixtures.
    drift_anomaly.build_drift_anomaly_response.cache_clear()
    monkeypatch.setattr(drift_anomaly, "_load_artifacts", _synthetic_artifacts_frames)
    yield
    drift_anomaly.build_drift_anomaly_response.cache_clear()


def _patch_lineage(monkeypatch: pytest.MonkeyPatch, result: ApiLineageResult) -> None:
    # Fake the startup evaluation so tests never touch real run manifests.
    monkeypatch.setattr(lineage_gate, "evaluate_lineage", lambda: result)


def _lineage(severity: str, *, is_valid: bool = True) -> ApiLineageResult:
    return ApiLineageResult(
        is_valid=is_valid, canonical_match=True, severity=severity, warnings=[]
    )


@pytest.mark.parametrize("severity", ["ok", "warning"])
def test_drift_anomaly_returns_200_envelope(
    monkeypatch: pytest.MonkeyPatch, severity: str
) -> None:
    _patch_lineage(monkeypatch, _lineage(severity))
    with TestClient(app) as client:
        resp = client.get("/api/v1/dashboard/drift-anomaly")
    assert resp.status_code == 200
    assert set(resp.json().keys()) == {"meta", "data"}


def test_drift_anomaly_meta_matches_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    with TestClient(app) as client:
        meta = client.get("/api/v1/dashboard/drift-anomaly").json()["meta"]
    assert meta["contractVersion"] == "1.0"
    assert meta["runId"] == "remat-v1-20260616T102558Z"
    assert meta["bomRunId"] == "20260612T124909Z"
    assert meta["dataGeneratedAt"] == "2026-06-16T10:25:58Z"
    # Exact equality locks keys, copy and order (notice presence is contract).
    assert meta["notices"] == _EXPECTED_NOTICES


def test_drift_anomaly_data_header_and_period(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lineage(monkeypatch, _lineage("warning"))
    with TestClient(app) as client:
        data = client.get("/api/v1/dashboard/drift-anomaly").json()["data"]
    assert set(data.keys()) == {
        "assetName",
        "datasetName",
        "periodStart",
        "periodEnd",
        "summaryKpis",
        "evidenceSeries",
        "detectionMethods",
        "affectedSignals",
        "insights",
    }
    assert data["assetName"] == "Pelletizer line"
    assert data["datasetName"] == "Real industrial dataset"
    assert data["periodStart"] == "2024-06-14"
    assert data["periodEnd"] == "2024-10-08"


def test_evidence_series_matches_ladder_and_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    with TestClient(app) as client:
        data = client.get("/api/v1/dashboard/drift-anomaly").json()["data"]
    series = data["evidenceSeries"]
    # Locks p95 (3 decimals), non-normal counts, residual counts and the
    # mapped §6 ladder (incl. drift day -> warning) in one comparison.
    assert series == _EXPECTED_SERIES
    # Locked decision: points carry `severity`, never `status`.
    assert all("status" not in point for point in series)


def test_evidence_series_omits_unscored_only_days(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    with TestClient(app) as client:
        data = client.get("/api/v1/dashboard/drift-anomaly").json()["data"]
    dates = [point["date"] for point in data["evidenceSeries"]]
    # 2024-01-05 has one row, but it is unscored-severity -> the day is omitted.
    assert "2024-01-05" not in dates
    assert all(point["anomalyScore"] != 0.99 for point in data["evidenceSeries"])


def test_residual_count_filters_scenario_and_suppression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    with TestClient(app) as client:
        data = client.get("/api/v1/dashboard/drift-anomaly").json()["data"]
    by_date = {point["date"]: point for point in data["evidenceSeries"]}
    # Suppressed rows and baseline-scenario rows never count: 01-01 has four
    # scenario rows but only two unsuppressed quarantine-scenario ones.
    assert by_date["2024-01-01"]["residualCount"] == 2
    # A scored day without scenario rows serves 0, not a missing point.
    assert by_date["2024-01-03"]["residualCount"] == 0
    # 2024-01-07 has a scenario row but no scored rows -> no series point.
    assert "2024-01-07" not in by_date


def test_summary_kpis_are_raw_numbers(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    with TestClient(app) as client:
        kpis = client.get("/api/v1/dashboard/drift-anomaly").json()["data"][
            "summaryKpis"
        ]
    assert [k["label"] for k in kpis] == [
        "Raw non-normal rows",
        "Contextualised for review",
        "Residual review backlog",
        "Healthy-only drift windows",
    ]
    # Funnel from the quarantine row of the synthetic rate table.
    assert [k["value"] for k in kpis] == [7, 4, 3, 9]
    for kpi in kpis:
        assert isinstance(kpi["value"], int)
        assert not isinstance(kpi["value"], str)


def test_detection_methods_order_and_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    with TestClient(app) as client:
        methods = client.get("/api/v1/dashboard/drift-anomaly").json()["data"][
            "detectionMethods"
        ]
    assert [m["method"] for m in methods] == [
        "statistical",
        "mahalanobis",
        "pca_t2",
        "pca_residual",
        "isolation_forest",
        "context_overlay",
    ]
    # Trigger tokens counted over non-normal rows only (the "statistical"
    # token on a normal row must not count); pca_residual serves the pca_q
    # trigger count; the overlay serves the suppressed-row count.
    assert [m["evidenceCount"] for m in methods] == [3, 1, 2, 3, 1, 4]


def test_detection_methods_no_fabricated_or_internal_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    with TestClient(app) as client:
        resp = client.get("/api/v1/dashboard/drift-anomaly")
    methods = [m["method"] for m in resp.json()["data"]["detectionMethods"]]
    # lof/ocsvm existed only in the demo (fabrication); pca_q is the internal
    # detector id and must never leak on the wire.
    assert "lof" not in methods
    assert "ocsvm" not in methods
    assert '"pca_q"' not in resp.text
    assert '"lof"' not in resp.text
    assert '"ocsvm"' not in resp.text
    overlay = resp.json()["data"]["detectionMethods"][-1]
    assert overlay["evidenceCount"] == 4
    assert "not a detector" in overlay["description"]


def test_affected_signals_dominant_listed_separately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    with TestClient(app) as client:
        signals = client.get("/api/v1/dashboard/drift-anomaly").json()["data"][
            "affectedSignals"
        ]
    dominant = signals[0]
    assert dominant["sensorId"] == "inlet_hopper_points"
    assert dominant["displayName"] == "Inlet hopper points counter"
    assert dominant["severity"] == "critical"
    assert dominant["contribution"] == "high"
    assert "pending human review" in dominant["interpretation"]


def test_affected_signals_terciles_and_display_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    with TestClient(app) as client:
        signals = client.get("/api/v1/dashboard/drift-anomaly").json()["data"][
            "affectedSignals"
        ]
    rest = signals[1:]
    assert [s["sensorId"] for s in rest] == [
        "inlet_hopper_humidity",
        "feeder_hopper_temp",
        "granulator_power",
    ]
    assert [s["displayName"] for s in rest] == [
        "Inlet hopper humidity",
        "Feeder hopper temperature",
        "Granulator power",
    ]
    # Tercile cutoffs over counts [3, 2, 1] with the pinned severity mapping:
    # only high-contribution process signals read as warning, never critical.
    assert [s["contribution"] for s in rest] == ["high", "medium", "low"]
    assert [s["severity"] for s in rest] == ["warning", "normal", "normal"]


def test_insights_interpolate_computed_numbers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    with TestClient(app) as client:
        resp = client.get("/api/v1/dashboard/drift-anomaly")
    insights = resp.json()["data"]["insights"]
    assert len(insights) == 3
    funnel_body = insights[0]["body"]
    # Numbers come from the synthetic rate row, proving interpolation.
    assert "7" in funnel_body and "4" in funnel_body and "3" in funnel_body
    assert "Inlet hopper points counter (4 rows)" in insights[1]["body"]
    # Real-run literals must not be hardcoded anywhere in the response.
    for literal in ("33,186", "30,096", "3,090", "33186", "30096", "3090"):
        assert literal not in resp.text


def test_drift_anomaly_json_is_camelcase(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    with TestClient(app) as client:
        data = client.get("/api/v1/dashboard/drift-anomaly").json()["data"]
    assert "summaryKpis" in data and "summary_kpis" not in data
    assert "evidenceSeries" in data and "evidence_series" not in data
    assert "detectionMethods" in data and "detection_methods" not in data
    assert "affectedSignals" in data and "affected_signals" not in data
    point = data["evidenceSeries"][0]
    assert "anomalyScore" in point and "anomaly_score" not in point
    assert "anomalyCount" in point and "anomaly_count" not in point
    assert "residualCount" in point and "residual_count" not in point
    signal = data["affectedSignals"][0]
    assert "sensorId" in signal and "sensor_id" not in signal
    assert "displayName" in signal and "display_name" not in signal
    method = data["detectionMethods"][0]
    assert "evidenceCount" in method and "evidence_count" not in method


def test_forbidden_framing_tripwire(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    with TestClient(app) as client:
        resp = client.get("/api/v1/dashboard/drift-anomaly")
    text = resp.text.lower()
    # §5.3: nothing is excluded/rescored; the quarantine is pending, original
    # scores are unchanged, and no confirmed failure is claimed.
    assert "excluded from scoring" not in text
    assert "exclude from automated scoring" not in text
    assert "reclassif" not in text
    assert "confirmed failure" not in text.replace("not confirmed failures", "")
    assert "unchanged" in text
    assert "pending" in text


def test_drift_anomaly_invalid_lineage_returns_503_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lineage(monkeypatch, _lineage("invalid", is_valid=False))
    with TestClient(app) as client:
        resp = client.get("/api/v1/dashboard/drift-anomaly")
    assert resp.status_code == 503
    assert resp.json() == _LINEAGE_INVALID_BODY


def test_drift_anomaly_unreadable_artifacts_return_503_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))

    def _raise() -> _Artifacts:
        raise ArtifactUnreadableError()

    monkeypatch.setattr(drift_anomaly, "_load_artifacts", _raise)
    with TestClient(app) as client:
        resp = client.get("/api/v1/dashboard/drift-anomaly")
    assert resp.status_code == 503
    assert resp.json() == _ARTIFACT_UNREADABLE_BODY


def test_drift_anomaly_response_is_cached_after_first_hit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    calls = {"count": 0}

    def _counting_loader() -> _Artifacts:
        calls["count"] += 1
        return _synthetic_artifacts_frames()

    monkeypatch.setattr(drift_anomaly, "_load_artifacts", _counting_loader)
    with TestClient(app) as client:
        first = client.get("/api/v1/dashboard/drift-anomaly")
        second = client.get("/api/v1/dashboard/drift-anomaly")
    assert first.status_code == 200
    assert second.status_code == 200
    assert calls["count"] == 1
    assert first.json() == second.json()
