"""Policy schema + source normalization (bursts, mappings, filters)."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError
from src.intelligence.incidents import sources
from src.intelligence.incidents.policy import (
    INCIDENT_STATUSES,
    INCIDENT_TYPES,
    RELATIONSHIP_TYPES,
    IncidentsPolicy,
)


def test_real_yaml_loads(incidents_policy: IncidentsPolicy) -> None:
    assert incidents_policy.suppression.enabled
    assert incidents_policy.forensic_addendum.enabled
    assert incidents_policy.grouping.recurring_collapse_types == [
        "sensor_warning",
        "context_shift",
        "data_quality_issue",
    ]


def test_unknown_key_raises() -> None:
    with pytest.raises(ValidationError):
        IncidentsPolicy.model_validate({"bursts": {"rate_treshold": 0.5}})


def test_taxonomies_are_the_contract() -> None:
    assert "anomaly_burst" in INCIDENT_TYPES
    assert "data_quality_issue" in INCIDENT_TYPES
    assert "pending_review" in INCIDENT_STATUSES
    assert set(RELATIONSHIP_TYPES) == {
        "temporally_adjacent",
        "overlaps",
        "contains",
        "possibly_explains",
        "corroborates",
        "shares_sensors",
        "shares_context",
        "follows",
        "unknown",
    }


def _sh_event(**overrides: object) -> dict[str, object]:
    base = {
        "sensor_health_event_id": "SH-1",
        "sensor": "s1",
        "start_timestamp": pd.Timestamp("2024-09-01"),
        "end_timestamp": pd.Timestamp("2024-09-02"),
        "duration_rows": 10,
        "duration_seconds": 86400.0,
        "status": "faulty",
        "issue_types": "flatline_zero",
        "max_health_score": 0.9,
        "affected_profiles": "mid_production",
        "evidence": "{}",
        "recommended_action": "inspect_sensor",
        "is_persistent": True,
        "review_status": "pending_review",
    }
    return {**base, **overrides}


def test_sensor_health_mapping() -> None:
    events = pd.DataFrame(
        [
            _sh_event(),  # persistent strong faulty -> sensor_fault critical
            _sh_event(
                sensor_health_event_id="SH-2",
                status="warning",
                issue_types="abrupt_offset",
                is_persistent=False,
            ),
            _sh_event(
                sensor_health_event_id="SH-3",
                issue_types="missingness_spike",
                is_persistent=False,
            ),  # missingness-only faulty -> data_quality_issue
        ]
    )
    out = sources.from_sensor_health(events)
    assert list(out["candidate_type"]) == [
        "sensor_fault",
        "sensor_warning",
        "data_quality_issue",
    ]
    assert out.iloc[0]["severity"] == "critical"
    assert out.iloc[1]["severity"] == "warning"


def test_anomaly_bursts_threshold_duration_and_gap(
    policy_factory: Callable[..., IncidentsPolicy],
) -> None:
    policy = policy_factory(
        bursts={
            "bucket_freq": "15min",
            "rate_threshold": 0.5,
            "min_duration_minutes": 30,
            "gap_merge_buckets": 1,
        }
    )
    n = 480
    ts = pd.date_range("2024-09-01", periods=n, freq="1min")
    severity = np.array(["normal"] * n, dtype=object)
    severity[120:200] = "anomaly"  # 80 min sustained burst
    severity[230:240] = "anomaly"  # 10 min blip: below min duration
    scores = pd.DataFrame(
        {
            "severity": severity,
            "profile": "mid_production",
            "affected_variables": np.where(severity == "anomaly", "s1|s2", ""),
            "triggered_detectors": np.where(severity == "anomaly", "statistical", ""),
        },
        index=ts,
    )
    bursts = sources.anomaly_bursts(scores, policy)
    assert len(bursts) == 1
    burst = bursts.iloc[0]
    assert burst["candidate_type"] == "anomaly_burst"
    assert burst["affected_sensors"].startswith("s1")
    assert pd.Timestamp(burst["start_timestamp"]) == pd.Timestamp("2024-09-01 02:00")


def test_context_transition_filter(
    policy_factory: Callable[..., IncidentsPolicy],
) -> None:
    policy = policy_factory()
    transitions = pd.DataFrame(
        [
            {
                "transition_timestamp": pd.Timestamp("2024-09-01 10:00"),
                "transition_types": "profile_change",  # routine: filtered out
            },
            {
                "transition_timestamp": pd.Timestamp("2024-09-01 11:00"),
                "transition_types": "steam_context_change",
            },
        ]
    )
    out = sources.from_context_transitions(transitions, policy)
    assert len(out) == 1
    assert out.iloc[0]["contexts"] == "steam_context_change"


def test_unsupported_sources_table() -> None:
    out = sources.unsupported_sources([("bom_context", "no_candidate_events")])
    assert list(out.columns) == ["source", "reason"]
    assert len(out) == 1
