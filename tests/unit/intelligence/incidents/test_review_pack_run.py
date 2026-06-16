"""Review pack (dedup, priority, context joins) + orchestrator CLI."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from src.intelligence.__main__ import _COMPONENTS
from src.intelligence.__main__ import main as dispatcher_main
from src.intelligence.incidents import actions as actions_mod
from src.intelligence.incidents import grouping, io, review_pack, run_incidents
from src.intelligence.incidents import relationships as relationships_mod
from src.intelligence.incidents.policy import IncidentsPolicy
from src.intelligence.incidents.validation import IncidentsBlockerError

CandidateFactory = Callable[..., pd.DataFrame]
PolicyFactory = Callable[..., IncidentsPolicy]

_END = pd.Timestamp("2024-10-08")


def _pack(
    candidates: pd.DataFrame,
    policy: IncidentsPolicy,
    timeline: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    incidents = grouping.group_candidates(candidates, policy, _END)
    relationships = relationships_mod.detect(incidents, policy)
    actions = actions_mod.recommend(incidents, policy)
    if timeline is None:
        timeline = pd.DataFrame()
    pack = review_pack.build(incidents, relationships, actions, timeline, policy)
    return pack, incidents


def test_priority_order_and_context_join(
    candidate_factory: CandidateFactory, policy_factory: PolicyFactory
) -> None:
    policy = policy_factory()
    ts = pd.date_range("2024-09-01", periods=600, freq="1h")
    timeline = pd.DataFrame(
        {
            "steam_context": "steam_conditioning_on",
            "sensor_health_context": "all_sensors_healthy",
            "product_code": "P1",
            "recipe_context_key": "R1",
        },
        index=ts,
    )
    candidates = candidate_factory(
        [
            {  # low-priority early context shift
                "candidate_type": "context_shift",
                "group_family": "context:steam",
                "severity": "info",
                "start_timestamp": "2024-09-01 10:00",
                "end_timestamp": "2024-09-01 10:00",
            },
            {  # critical persistent sensor fault: must rank first
                "candidate_type": "sensor_fault",
                "group_family": "s1:flatline_zero",
                "affected_sensors": "s1",
                "severity": "critical",
                "is_persistent": True,
                "start_timestamp": "2024-09-17 16:00",
                "end_timestamp": "2024-10-08 14:00",
            },
            {  # anomaly-severity drift
                "candidate_type": "process_drift",
                "group_family": "sensor:process_drift",
                "affected_sensors": "s2",
                "severity": "anomaly",
                "start_timestamp": "2024-09-10 00:00",
                "end_timestamp": "2024-09-11 00:00",
            },
        ]
    )
    pack, _ = _pack(candidates, policy, timeline)
    assert list(pack["incident_type"])[:2] == ["sensor_fault", "process_drift"]
    fault = pack.iloc[0]
    assert fault["steam_contexts"] == "steam_conditioning_on"
    assert fault["product_codes"] == "P1"
    assert "quarantine_from_process_scoring" in fault["recommended_actions"]
    assert fault["review_status"] == "pending_review"


def test_temporal_dedup_collapses_near_identical_rows(
    candidate_factory: CandidateFactory, policy_factory: PolicyFactory
) -> None:
    policy = policy_factory(review_pack={"dedup_overlap_fraction": 0.8})
    candidates = candidate_factory(
        [
            {
                "candidate_type": "multivariate_shift",
                "group_family": "multivariate:multivariate_shift",
                "severity": "critical",
                "start_timestamp": "2024-09-17 00:00",
                "end_timestamp": "2024-09-25 00:00",
            },
            {  # same span, different family -> separate incident, deduped in pack
                "candidate_type": "multivariate_shift",
                "group_family": "multivariate:other_family",
                "severity": "anomaly",
                "start_timestamp": "2024-09-17 12:00",
                "end_timestamp": "2024-09-25 00:00",
            },
        ]
    )
    pack, incidents = _pack(candidates, policy)
    assert len(incidents) == 2  # incidents.parquet keeps both
    assert len(pack) == 1  # the pack collapses them
    assert pack.iloc[0]["severity"] == "critical"
    assert incidents.iloc[1]["incident_id"] in pack.iloc[0]["related_incident_ids"]


def test_max_rows_truncation(
    candidate_factory: CandidateFactory, policy_factory: PolicyFactory
) -> None:
    policy = policy_factory(review_pack={"max_rows": 3})
    rows = [
        {
            "candidate_type": "process_drift",
            "group_family": "sensor:process_drift",
            "affected_sensors": f"s{i}",
            "start_timestamp": f"2024-09-{i + 1:02d} 00:00",
            "end_timestamp": f"2024-09-{i + 1:02d} 06:00",
        }
        for i in range(8)
    ]
    pack, incidents = _pack(candidate_factory(rows), policy)
    assert len(incidents) == 8
    assert len(pack) == 3


def test_no_write_writes_nothing(incidents_world: dict[str, Any]) -> None:
    assert run_incidents.main([*incidents_world["args"], "--no-write"]) == 0
    assert not incidents_world["out_root"].exists()
    assert not incidents_world["addendum_root"].exists()


def test_full_run_with_addendum(incidents_world: dict[str, Any]) -> None:
    assert run_incidents.main([*incidents_world["args"], "--run-id", "t1"]) == 0
    out = incidents_world["out_root"] / "runs" / "t1"

    manifest = json.loads((out / io.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["completion_status"] == "complete"
    assert manifest["addendum_status"] == "complete"
    assert manifest["drift_run_id"] == "d1"
    assert (
        io.resolve_run(incidents_world["out_root"], "latest", io.MANIFEST_NAME) == out
    )

    for rel in (
        io.INCIDENTS_FILE,
        io.RELATIONSHIPS_FILE,
        io.REVIEW_PACK_FILE,
        io.TIMELINE_FILE,
        io.SUMMARY_FILE,
        io.ACTIONS_FILE,
        io.SUPPRESSED_FILE,
        io.UNSUPPORTED_FILE,
    ):
        assert (out / rel).exists(), rel

    incidents = pd.read_parquet(out / io.INCIDENTS_FILE)
    assert (incidents["review_status"] == "pending_review").all()
    fault = incidents[
        (incidents["incident_type"] == "sensor_fault")
        & incidents["affected_sensors"].str.contains("inlet_hopper_points")
    ]
    assert len(fault) == 1  # drift + sensor_health sources merged
    assert set(fault.iloc[0]["sources"].split("|")) == {"drift", "sensor_health"}
    assert fault.iloc[0]["status"] == "persistent"
    assert fault.iloc[0]["severity"] == "critical"

    suppressed = pd.read_parquet(out / io.SUPPRESSED_FILE)
    assert len(suppressed) == 1  # the burst inside the fault window
    relationships = pd.read_parquet(out / io.RELATIONSHIPS_FILE)
    assert (relationships["causality_status"] == "unknown").all()

    addendum = incidents_world["addendum_root"] / "t1"
    addendum_manifest = json.loads(
        (addendum / io.ADDENDUM_MANIFEST_NAME).read_text(encoding="utf-8")
    )
    assert addendum_manifest["completion_status"] == "complete"
    for figure in (
        "raw_vs_healthy_only_drift.png",
        "drift_by_sensor_health_context.png",
        "drift_by_steam_context.png",
        "top_drift_events_timeline.png",
        "incident_timeline.png",
    ):
        assert (addendum / "figures" / figure).exists(), figure
    summary = (addendum / "executive_summary.md").read_text(encoding="utf-8")
    assert "interpretive" in summary
    limitations = (addendum / "limitations.md").read_text(encoding="utf-8")
    assert "causality" in limitations


def test_skip_addendum(incidents_world: dict[str, Any]) -> None:
    assert (
        run_incidents.main(
            [*incidents_world["args"], "--run-id", "t2", "--skip-addendum"]
        )
        == 0
    )
    out = incidents_world["out_root"] / "runs" / "t2"
    manifest = json.loads((out / io.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["addendum_status"] == "skipped"
    assert not (incidents_world["addendum_root"] / "t2").exists()


def test_manifest_written_last_failed_run_not_resolvable(
    incidents_world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    original = io.write_table

    def explode(frame: pd.DataFrame, path: Path) -> None:
        if path.name == io.REVIEW_PACK_FILE.name:
            raise OSError("disk full")
        original(frame, path)

    monkeypatch.setattr(io, "write_table", explode)
    with pytest.raises(OSError, match="disk full"):
        run_incidents.main([*incidents_world["args"], "--run-id", "crashed"])
    out_root = incidents_world["out_root"]
    assert not (out_root / "runs" / "crashed" / io.MANIFEST_NAME).exists()
    with pytest.raises(FileNotFoundError):
        io.resolve_run(out_root, "latest", io.MANIFEST_NAME)


def test_dispatcher_registration(incidents_world: dict[str, Any]) -> None:
    assert "incidents" in _COMPONENTS
    assert (
        dispatcher_main(
            ["--component", "incidents", *incidents_world["args"], "--no-write"]
        )
        == 0
    )


def test_upstream_run_divergence_is_a_blocker(incidents_world: dict[str, Any]) -> None:
    """DAT-01: a drift run pinning a different sensor-health run fails closed."""
    dmanifest = (
        incidents_world["tmp_path"] / "drift" / "runs" / "d1" / "drift_manifest.json"
    )
    payload = json.loads(dmanifest.read_text(encoding="utf-8"))
    payload["upstream"]["sensor_health_run_id"] = "a-different-run"
    dmanifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(IncidentsBlockerError, match="divergence"):
        run_incidents.main([*incidents_world["args"], "--no-write"])
