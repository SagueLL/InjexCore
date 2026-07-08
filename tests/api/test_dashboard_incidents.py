"""Incidents endpoint: full-list contract, mappings, sorting + fail-closed gates."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from src.api.errors import ArtifactUnreadableError
from src.api.main import app
from src.api.services import incidents, lineage_gate
from src.api.services.lineage_gate import ApiLineageResult
from src.dashboard.contract import CANONICAL_RUN_ID
from src.intelligence.incidents import io as incidents_io

_EXPECTED_NOTICES = [
    {
        "key": "relationships_associative",
        "text": "Incident relationships are associative, not causal.",
    },
    {
        "key": "quarantine_pending",
        "text": "Quarantine is pending review and not approved.",
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

# §1 sort: pack order first (warning before critical proves pack rank beats
# severity), then non-pack by source-severity rank (anomaly before info).
_EXPECTED_ORDER = [
    "inc-pack-warning",
    "inc-pack-fault",
    "inc-open-anomaly",
    "inc-open-info",
]

_CANONICAL_RUN = incidents_io.run_dir(incidents_io.INCIDENTS_DIR, CANONICAL_RUN_ID)
requires_real_run = pytest.mark.skipif(
    not (_CANONICAL_RUN / incidents_io.MANIFEST_NAME).exists(),
    reason="canonical incidents run artifacts not present",
)


def _synthetic_frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    frame = pd.DataFrame(
        {
            "incident_id": [
                "inc-pack-warning",
                "inc-pack-fault",
                "inc-open-anomaly",
                "inc-open-info",
                "inc-suppressed",
            ],
            "incident_type": [
                "process_drift",
                "sensor_fault",
                "anomaly_burst",
                "context_shift",
                "anomaly_burst",
            ],
            "severity": ["warning", "critical", "anomaly", "info", "critical"],
            "status": ["resolved", "persistent", "resolved", "resolved", "resolved"],
            "review_status": ["pending_review"] * 5,
            "start_timestamp": pd.to_datetime(
                [
                    "2024-07-02 08:00:00",
                    # Same UTC day start/end -> startDate == endDate.
                    "2024-09-17 03:00:00",
                    "2024-08-05 10:00:00",
                    "2024-06-20 00:00:00",
                    "2024-08-01 00:00:00",
                ]
            ),
            "end_timestamp": pd.to_datetime(
                [
                    "2024-07-03 18:00:00",
                    "2024-09-17 21:00:00",
                    "2024-08-06 12:00:00",
                    "2024-06-21 06:00:00",
                    "2024-08-02 00:00:00",
                ]
            ),
            "duration_seconds": [122400.0, 64800.0, 93600.0, 108000.0, 86400.0],
            "n_members": [4, 12, 3, 2, 5],
            "sources": [
                "drift",
                "sensor_health",
                "anomaly|drift",
                "operational_context",
                "anomaly",
            ],
            "affected_sensors": [
                "feeder_speed|screw_pressure",
                "inlet_hopper_points",  # quarantine channel -> contextualised
                "motor_current",
                "",  # empty -> affectedSignals == []
                "motor_current",
            ],
        }
    )
    review_pack = pd.DataFrame({"incident_id": ["inc-pack-warning", "inc-pack-fault"]})
    suppressed = pd.DataFrame({"suppressed_incident_id": ["inc-suppressed"]})
    actions = pd.DataFrame(
        {
            "incident_id": [
                "inc-pack-fault",
                "inc-pack-warning",
                "inc-open-anomaly",
                "inc-open-anomaly",
            ],
            "recommended_action": [
                "quarantine_from_process_scoring",
                "review_setpoint_changes",
                "review_operator_notes",  # low priority, listed first on purpose
                "inspect_sensor_channel",  # high priority, must lead the copy
            ],
            "priority": ["high", "medium", "low", "high"],
            "approval_required": [True, False, False, False],
            "approved": [False, False, False, False],
        }
    )
    unsuppressed = frame[
        ~frame["incident_id"].isin(suppressed["suppressed_incident_id"])
    ].reset_index(drop=True)
    return unsuppressed, review_pack, actions


@pytest.fixture(autouse=True)
def _fresh_cache() -> Iterator[None]:
    # Unconditional (unlike the loader patch below): a leaked cached envelope
    # — synthetic OR real — would silently decouple later tests from fixtures.
    incidents.build_incidents_response.cache_clear()
    yield
    incidents.build_incidents_response.cache_clear()


@pytest.fixture
def synthetic_artifacts(monkeypatch: pytest.MonkeyPatch) -> None:
    # Opt-in rather than autouse: the real-artifact integration test below
    # needs the genuine loader.
    monkeypatch.setattr(incidents, "_load_artifacts", _synthetic_frames)


def _patch_lineage(monkeypatch: pytest.MonkeyPatch, result: ApiLineageResult) -> None:
    # Fake the startup evaluation so tests never touch real run manifests.
    monkeypatch.setattr(lineage_gate, "evaluate_lineage", lambda: result)


def _lineage(severity: str, *, is_valid: bool = True) -> ApiLineageResult:
    return ApiLineageResult(
        is_valid=is_valid, canonical_match=True, severity=severity, warnings=[]
    )


def _get_incidents(
    monkeypatch: pytest.MonkeyPatch, severity: str = "ok"
) -> httpx.Response:
    _patch_lineage(monkeypatch, _lineage(severity))
    with TestClient(app) as client:
        return client.get("/api/v1/dashboard/incidents")


@pytest.mark.parametrize("severity", ["ok", "warning"])
def test_incidents_returns_200_envelope(
    monkeypatch: pytest.MonkeyPatch, synthetic_artifacts: None, severity: str
) -> None:
    resp = _get_incidents(monkeypatch, severity)
    assert resp.status_code == 200
    assert set(resp.json().keys()) == {"meta", "data"}


def test_incidents_meta_matches_contract(
    monkeypatch: pytest.MonkeyPatch, synthetic_artifacts: None
) -> None:
    meta = _get_incidents(monkeypatch).json()["meta"]
    assert meta["contractVersion"] == "1.1"
    assert meta["runId"] == "remat-v1-20260616T102558Z"
    assert meta["bomRunId"] == "20260612T124909Z"
    assert meta["dataGeneratedAt"] == "2026-06-16T14:51:48Z"
    # Exact equality locks keys, copy and order (notice presence is contract).
    assert meta["notices"] == _EXPECTED_NOTICES


def test_incidents_data_header_and_period(
    monkeypatch: pytest.MonkeyPatch, synthetic_artifacts: None
) -> None:
    data = _get_incidents(monkeypatch, "warning").json()["data"]
    assert set(data.keys()) == {
        "assetName",
        "datasetName",
        "periodStart",
        "periodEnd",
        "summaryKpis",
        "severityDistribution",
        "incidents",
        "insights",
    }
    assert data["assetName"] == "Pelletizer line"
    assert data["datasetName"] == "Real industrial dataset"
    assert data["periodStart"] == "2024-06-14"
    assert data["periodEnd"] == "2024-10-08"
    assert data["summaryKpis"]
    assert data["severityDistribution"]
    assert data["insights"]


def test_incidents_severity_distribution_sums_and_labels(
    monkeypatch: pytest.MonkeyPatch, synthetic_artifacts: None
) -> None:
    data = _get_incidents(monkeypatch).json()["data"]
    # Four fixed rows preserving the backend 4-tier truth in the labels; the
    # two UI-critical rows stay distinguishable ("Anomaly evidence"/"Critical").
    assert data["severityDistribution"] == [
        {"severity": "normal", "label": "Normal", "count": 1},
        {"severity": "warning", "label": "Warning", "count": 1},
        {"severity": "critical", "label": "Anomaly evidence", "count": 1},
        {"severity": "critical", "label": "Critical", "count": 1},
    ]
    total = sum(row["count"] for row in data["severityDistribution"])
    assert total == len(data["incidents"])


def test_incident_records_fields_and_enums(
    monkeypatch: pytest.MonkeyPatch, synthetic_artifacts: None
) -> None:
    records = _get_incidents(monkeypatch).json()["data"]["incidents"]
    assert set(records[0].keys()) == {
        "id",
        "title",
        "severity",
        "status",
        "startDate",
        "endDate",
        "affectedSignals",
        "evidenceSummary",
        "recommendation",
        "sourceSeverity",
        "sourceStatus",
        "reviewStatus",
        "startTimestamp",
        "endTimestamp",
    }
    assert {r["severity"] for r in records} <= {"normal", "warning", "critical"}
    # "closed" is reserved and must never be emitted in v1 (§5.3).
    assert {r["status"] for r in records} <= {"open", "in_review", "contextualised"}
    by_id = {r["id"]: r for r in records}
    fault = by_id["inc-pack-fault"]
    # Sub-day incident: day truncation is contract-legal, full-ISO truth stays.
    assert fault["startDate"] == fault["endDate"] == "2024-09-17"
    assert fault["startTimestamp"] == "2024-09-17T03:00:00Z"
    assert fault["endTimestamp"] == "2024-09-17T21:00:00Z"
    assert by_id["inc-open-info"]["affectedSignals"] == []
    assert by_id["inc-pack-warning"]["affectedSignals"] == [
        "Feeder speed",
        "Screw pressure",
    ]


def test_incidents_status_mapping(
    monkeypatch: pytest.MonkeyPatch, synthetic_artifacts: None
) -> None:
    records = _get_incidents(monkeypatch).json()["data"]["incidents"]
    # §5 ladder: contextualised (quarantine channel) beats pack membership;
    # pack membership beats open; backend "resolved" never becomes "closed".
    assert {r["id"]: r["status"] for r in records} == {
        "inc-pack-warning": "in_review",
        "inc-pack-fault": "contextualised",
        "inc-open-anomaly": "open",
        "inc-open-info": "open",
    }


def test_incidents_language_tripwires(
    monkeypatch: pytest.MonkeyPatch, synthetic_artifacts: None
) -> None:
    resp = _get_incidents(monkeypatch)
    # §5.3 forbidden framing: evidence windows, never confirmed failures;
    # quarantine is pending, nothing is excluded automatically.
    text = resp.text.lower()
    assert "confirmed failure" not in text
    assert "excluded from scoring" not in text
    assert "exclude from automated scoring" not in text
    by_id = {r["id"]: r for r in resp.json()["data"]["incidents"]}
    assert "pending" in by_id["inc-pack-fault"]["recommendation"]


def test_incidents_json_is_camelcase_and_kpis_raw_numbers(
    monkeypatch: pytest.MonkeyPatch, synthetic_artifacts: None
) -> None:
    data = _get_incidents(monkeypatch).json()["data"]
    record = data["incidents"][0]
    assert "affectedSignals" in record and "affected_signals" not in record
    assert "evidenceSummary" in record and "evidence_summary" not in record
    assert "sourceSeverity" in record and "source_severity" not in record
    assert "summaryKpis" in data and "summary_kpis" not in data
    assert "severityDistribution" in data and "severity_distribution" not in data
    kpis = data["summaryKpis"]
    assert [k["label"] for k in kpis] == [
        "Total incidents",
        "Critical evidence windows",
        "In review",
        "Contextualised",
    ]
    # Critical KPI counts the UI-critical tier: anomaly + critical sources.
    assert [k["value"] for k in kpis] == [4, 2, 1, 1]
    for kpi in kpis:
        assert isinstance(kpi["value"], int)
        assert not isinstance(kpi["value"], str)


def test_incidents_sorting_pack_first_then_severity(
    monkeypatch: pytest.MonkeyPatch, synthetic_artifacts: None
) -> None:
    records = _get_incidents(monkeypatch).json()["data"]["incidents"]
    assert [r["id"] for r in records] == _EXPECTED_ORDER


def test_incidents_recommendations_follow_action_priority(
    monkeypatch: pytest.MonkeyPatch, synthetic_artifacts: None
) -> None:
    records = _get_incidents(monkeypatch).json()["data"]["incidents"]
    by_id = {r["id"]: r["recommendation"] for r in records}
    # High-priority action leads even though the low one is persisted first.
    assert by_id["inc-open-anomaly"].startswith("Inspect the affected sensor channel")
    # No persisted actions -> curated fallback copy.
    assert by_id["inc-open-info"].startswith("Review against plant records")


def test_incidents_invalid_lineage_returns_503_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No synthetic fixture needed: the gate fires before the loader runs.
    resp = _get_incidents(monkeypatch, "invalid")
    assert resp.status_code == 503
    assert resp.json() == _LINEAGE_INVALID_BODY


def test_incidents_unreadable_artifacts_return_503_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        raise ArtifactUnreadableError()

    monkeypatch.setattr(incidents, "_load_artifacts", _raise)
    resp = _get_incidents(monkeypatch)
    assert resp.status_code == 503
    assert resp.json() == _ARTIFACT_UNREADABLE_BODY


def test_incidents_response_is_cached_after_first_hit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lineage(monkeypatch, _lineage("ok"))
    calls = {"count": 0}

    def _counting_loader() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        calls["count"] += 1
        return _synthetic_frames()

    monkeypatch.setattr(incidents, "_load_artifacts", _counting_loader)
    with TestClient(app) as client:
        first = client.get("/api/v1/dashboard/incidents")
        second = client.get("/api/v1/dashboard/incidents")
    assert first.status_code == 200
    assert second.status_code == 200
    assert calls["count"] == 1
    assert first.json() == second.json()


@requires_real_run
def test_incidents_real_artifacts_serve_all_88(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Genuine loader on purpose: locks the endpoint to the pinned canonical
    # run's full incident surface, not a lossy subset of the review pack.
    resp = _get_incidents(monkeypatch, "warning")
    assert resp.status_code == 200
    data = resp.json()["data"]
    records = data["incidents"]
    assert len(records) == 88
    # KNOWN UPSTREAM DEFECT (before-pilot): the canonical run's incident ids are
    # not unique. INC-process_drift-20240925T000000Z-8743 names two genuinely
    # different incidents (warning/conditioner_steam_loop_temp and
    # anomaly/granulator_power), so _pack_rank and actions_by_incident silently
    # share one rank and one action set across both. Pinned here so the fix in
    # src/intelligence/incidents/ (id generation) is forced to update this
    # assertion rather than land unnoticed. Do not "fix" this by deduplicating
    # at the API — that would hide a real data-integrity defect.
    assert len({r["id"] for r in records}) == 87
    assert [row["count"] for row in data["severityDistribution"]] == [3, 48, 27, 10]
    statuses = {r["status"] for r in records}
    assert "closed" not in statuses
    assert {"contextualised", "in_review"} <= statuses
    # First served incident is the review pack's top-priority row.
    review_pack = pd.read_parquet(_CANONICAL_RUN / incidents_io.REVIEW_PACK_FILE)
    assert records[0]["id"] == review_pack["incident_id"].iloc[0]
    text = resp.text.lower()
    assert "confirmed failure" not in text
    assert "excluded from scoring" not in text
    assert "exclude from automated scoring" not in text
