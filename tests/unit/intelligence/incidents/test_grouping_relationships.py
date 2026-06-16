"""Grouping, recurring collapse, cross-source merge, suppression, relationships."""

from __future__ import annotations

import json
from collections.abc import Callable

import pandas as pd
from src.intelligence.incidents import actions as actions_mod
from src.intelligence.incidents import grouping
from src.intelligence.incidents import relationships as relationships_mod
from src.intelligence.incidents.policy import IncidentsPolicy

_END = pd.Timestamp("2024-10-08")

CandidateFactory = Callable[..., pd.DataFrame]
PolicyFactory = Callable[..., IncidentsPolicy]


def test_temporal_adjacency_merges_within_gap(
    candidate_factory: CandidateFactory, policy_factory: PolicyFactory
) -> None:
    policy = policy_factory(grouping={"sensor_health_max_gap_minutes": 240})
    candidates = candidate_factory(
        [
            {
                "candidate_type": "sensor_fault",
                "group_family": "s1:flatline_zero",
                "affected_sensors": "s1",
                "start_timestamp": "2024-09-01 10:00",
                "end_timestamp": "2024-09-01 12:00",
            },
            {  # 2h gap: merges
                "candidate_type": "sensor_fault",
                "group_family": "s1:flatline_zero",
                "affected_sensors": "s1",
                "start_timestamp": "2024-09-01 14:00",
                "end_timestamp": "2024-09-01 16:00",
            },
            {  # 20h gap: separate incident
                "candidate_type": "sensor_fault",
                "group_family": "s1:flatline_zero",
                "affected_sensors": "s1",
                "start_timestamp": "2024-09-02 12:00",
                "end_timestamp": "2024-09-02 13:00",
            },
        ]
    )
    incidents = grouping.group_candidates(candidates, policy, _END)
    assert len(incidents) == 2
    assert incidents.iloc[0]["n_members"] == 2
    assert (incidents["review_status"] == "pending_review").all()


def test_jaccard_gate_keeps_different_sensors_apart(
    candidate_factory: CandidateFactory, policy_factory: PolicyFactory
) -> None:
    policy = policy_factory()
    candidates = candidate_factory(
        [
            {
                "group_family": "sensor:process_drift",
                "affected_sensors": "s1",
                "start_timestamp": "2024-09-01 10:00",
                "end_timestamp": "2024-09-01 12:00",
            },
            {
                "group_family": "sensor:process_drift",
                "affected_sensors": "s2",  # disjoint sensors: stays separate
                "start_timestamp": "2024-09-01 12:30",
                "end_timestamp": "2024-09-01 13:00",
            },
        ]
    )
    incidents = grouping.group_candidates(candidates, policy, _END)
    assert len(incidents) == 2


def test_recurring_collapse_only_for_routine_types(
    candidate_factory: CandidateFactory, policy_factory: PolicyFactory
) -> None:
    policy = policy_factory(grouping={"recurring_collapse_min": 3})
    rows = []
    for day in range(1, 7):
        rows.append(
            {
                "candidate_type": "sensor_warning",
                "group_family": "s1:variance_explosion",
                "affected_sensors": "s1",
                "source": "sensor_health",
                "start_timestamp": f"2024-09-{day:02d} 10:00",
                "end_timestamp": f"2024-09-{day:02d} 11:00",
            }
        )
        rows.append(
            {
                "candidate_type": "anomaly_burst",
                "group_family": "anomaly_burst",
                "source": "anomaly",
                "start_timestamp": f"2024-09-{day:02d} 12:00",
                "end_timestamp": f"2024-09-{day:02d} 13:00",
            }
        )
    incidents = grouping.group_candidates(candidate_factory(rows), policy, _END)
    collapsed = grouping.collapse_recurring(incidents, policy, _END)
    warnings = collapsed[collapsed["incident_type"] == "sensor_warning"]
    bursts = collapsed[collapsed["incident_type"] == "anomaly_burst"]
    assert len(warnings) == 1  # routine pattern -> one reviewable incident
    assert json.loads(warnings.iloc[0]["evidence"])["recurring_pattern"] is True
    assert len(bursts) == 6  # bursts are never collapsed


def test_cross_source_merge_unifies_same_episode(
    candidate_factory: CandidateFactory, policy_factory: PolicyFactory
) -> None:
    policy = policy_factory()
    candidates = candidate_factory(
        [
            {
                "candidate_type": "sensor_fault",
                "group_family": "s1:flatline_zero",
                "source": "sensor_health",
                "affected_sensors": "s1",
                "severity": "critical",
                "is_persistent": True,
                "start_timestamp": "2024-09-17 16:23",
                "end_timestamp": "2024-10-08 14:00",
            },
            {
                "candidate_type": "sensor_fault",
                "group_family": "sensor:sensor_drift",
                "source": "drift",
                "affected_sensors": "s1",
                "severity": "critical",
                "is_persistent": True,
                "start_timestamp": "2024-09-17 16:23",
                "end_timestamp": "2024-10-08 14:00",
            },
        ]
    )
    incidents = grouping.group_candidates(candidates, policy, _END)
    assert len(incidents) == 2  # different families: grouping keeps them apart
    merged = grouping.merge_cross_source(incidents, policy)
    assert len(merged) == 1  # same sensor + same episode -> one incident
    survivor = merged.iloc[0]
    assert set(survivor["sources"].split("|")) == {"drift", "sensor_health"}
    assert survivor["status"] == "persistent"
    assert "merged_from" in survivor["evidence"]


def test_suppression_requires_coverage_and_shared_sensors(
    candidate_factory: CandidateFactory, policy_factory: PolicyFactory
) -> None:
    policy = policy_factory(
        suppression={"coverage_fraction": 0.7, "require_shared_sensors": True}
    )
    candidates = candidate_factory(
        [
            {
                "candidate_type": "sensor_fault",
                "group_family": "s1:flatline_zero",
                "affected_sensors": "s1",
                "severity": "critical",
                "is_persistent": True,
                "start_timestamp": "2024-09-17 16:00",
                "end_timestamp": "2024-10-08 14:00",
            },
            {  # covered + shared sensor -> suppressed
                "candidate_type": "anomaly_burst",
                "group_family": "anomaly_burst",
                "source": "anomaly",
                "affected_sensors": "s1|s2",
                "severity": "anomaly",
                "start_timestamp": "2024-09-17 17:00",
                "end_timestamp": "2024-10-08 13:00",
            },
            {  # outside the fault window -> kept
                "candidate_type": "anomaly_burst",
                "group_family": "anomaly_burst",
                "source": "anomaly",
                "affected_sensors": "s1",
                "severity": "anomaly",
                "start_timestamp": "2024-09-01 10:00",
                "end_timestamp": "2024-09-01 12:00",
            },
        ]
    )
    incidents = grouping.group_candidates(candidates, policy, _END)
    kept, suppressed = grouping.suppress_duplicates(incidents, policy)
    assert len(suppressed) == 1
    assert suppressed.iloc[0]["reason"] == "burst_explained_by_sensor_fault"
    assert suppressed.iloc[0]["coverage"] > 0.9
    kept_bursts = kept[kept["incident_type"] == "anomaly_burst"]
    assert len(kept_bursts) == 1  # the pre-fault burst survives


def test_relationships_types_and_causality_unknown(
    candidate_factory: CandidateFactory, policy_factory: PolicyFactory
) -> None:
    policy = policy_factory()
    candidates = candidate_factory(
        [
            {
                "candidate_type": "sensor_fault",
                "group_family": "s1:flatline_zero",
                "affected_sensors": "s1",
                "severity": "critical",
                "is_persistent": True,
                "start_timestamp": "2024-09-17 16:00",
                "end_timestamp": "2024-10-08 14:00",
            },
            {
                "candidate_type": "multivariate_shift",
                "group_family": "multivariate:multivariate_shift",
                "affected_sensors": "s1",  # shares the faulty sensor
                "start_timestamp": "2024-09-18 00:00",
                "end_timestamp": "2024-09-25 00:00",
            },
            {
                "candidate_type": "context_shift",
                "group_family": "context:steam",
                "contexts": "steam_context_change",
                "start_timestamp": "2024-09-17 18:00",
                "end_timestamp": "2024-09-17 18:00",
            },
        ]
    )
    incidents = grouping.group_candidates(candidates, policy, _END)
    relationships = relationships_mod.detect(incidents, policy)
    assert len(relationships)
    assert (relationships["causality_status"] == "unknown").all()
    types = set(relationships["relationship_type"])
    assert "contains" in types
    assert "possibly_explains" in types  # fault contains + shares s1 with the shift
    explains = relationships[relationships["relationship_type"] == "possibly_explains"]
    fault_id = incidents[incidents["incident_type"] == "sensor_fault"].iloc[0][
        "incident_id"
    ]
    assert (explains["source_incident_id"] == fault_id).all()
    # INC-01: evidence names the actual shared sensor(s); never claimed falsely.
    ev = json.loads(explains.iloc[0]["evidence"])
    assert ev["basis"] == "interval_overlap_and_shared_sensors"
    assert ev["sensors"] == ["s1"]


def test_possibly_explains_requires_shared_sensors(
    candidate_factory: CandidateFactory, policy_factory: PolicyFactory
) -> None:
    """INC-01: interval overlap without shared sensors does NOT possibly_explain."""
    policy = policy_factory()
    candidates = candidate_factory(
        [
            {
                "candidate_type": "sensor_fault",
                "group_family": "s1:flatline_zero",
                "affected_sensors": "s1",
                "severity": "critical",
                "is_persistent": True,
                "start_timestamp": "2024-09-17 16:00",
                "end_timestamp": "2024-10-08 14:00",
            },
            {
                "candidate_type": "anomaly_burst",
                "group_family": "anomaly_burst:anomaly_burst",
                "affected_sensors": "s2",  # different sensor — no overlap
                "start_timestamp": "2024-09-18 00:00",
                "end_timestamp": "2024-09-25 00:00",
            },
        ]
    )
    incidents = grouping.group_candidates(candidates, policy, _END)
    relationships = relationships_mod.detect(incidents, policy)
    types = set(relationships["relationship_type"])
    # The fault still *contains* the burst temporally, but cannot explain it.
    assert "contains" in types
    assert "possibly_explains" not in types
    assert "shares_sensors" not in types


def test_actions_quarantine_flags_hardcoded(
    candidate_factory: CandidateFactory, policy_factory: PolicyFactory
) -> None:
    policy = policy_factory()
    candidates = candidate_factory(
        [
            {
                "candidate_type": "sensor_fault",
                "group_family": "s1:counter_reset|flatline_zero",
                "affected_sensors": "s1",
                "severity": "critical",
                "is_persistent": True,
                "evidence": '{"issue_types":"flatline_zero|counter_reset:x"}',
                "start_timestamp": "2024-09-17 16:00",
                "end_timestamp": "2024-10-08 14:00",
            },
            {
                "candidate_type": "process_drift",
                "group_family": "sensor:process_drift",
                "affected_sensors": "s2",
                "start_timestamp": "2024-09-01 10:00",
                "end_timestamp": "2024-09-02 10:00",
            },
        ]
    )
    incidents = grouping.group_candidates(candidates, policy, _END)
    actions = actions_mod.recommend(incidents, policy)
    quarantine = actions[actions["recommended_action"] == actions_mod.QUARANTINE_ACTION]
    assert len(quarantine) == 1
    assert bool(quarantine.iloc[0]["approval_required"]) is True
    assert bool(quarantine.iloc[0]["approved"]) is False
    assert (actions["approved"] == False).all()  # noqa: E712 — column-wide check
    fault_actions = set(
        actions[actions["incident_id"] == quarantine.iloc[0]["incident_id"]][
            "recommended_action"
        ]
    )
    assert "inspect_sensor_channel" in fault_actions
    assert "inspect_counter_reset" in fault_actions
    drift_actions = set(
        actions[
            actions["incident_id"]
            == incidents[incidents["incident_type"] == "process_drift"].iloc[0][
                "incident_id"
            ]
        ]["recommended_action"]
    )
    assert "compare_healthy_only_drift" in drift_actions
