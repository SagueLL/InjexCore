"""Scoring (caps, weights, calibration, override) and event aggregation."""

from __future__ import annotations

import json
from collections.abc import Callable

import pandas as pd
import pytest
from src.intelligence.drift import events as events_mod
from src.intelligence.drift import scoring
from src.intelligence.drift.policy import DriftPolicy

_HOUR = pd.Timedelta("1h")


def _metric_rows(
    values: list[float],
    *,
    metric: str = "psi",
    entity: str = "s1",
    scope: str = "sensor",
    view: str = "raw",
    start: str = "2024-06-01",
) -> pd.DataFrame:
    windows = pd.date_range(start, periods=len(values), freq="1h")
    return pd.DataFrame(
        {
            "window_start": windows,
            "scope": scope,
            "view": view,
            "entity": entity,
            "profile": "__global__",
            "metric": metric,
            "value": values,
            "n_rows": 60,
            "n_valid": 60,
        }
    )


def _score(
    rows: pd.DataFrame, policy: DriftPolicy, train_end: str = "2100-01-01"
) -> pd.DataFrame:
    return scoring.normalize_and_score(rows, policy, _HOUR, pd.Timestamp(train_end))


def test_caps_and_weights(policy_factory: Callable[..., DriftPolicy]) -> None:
    policy = policy_factory(
        scoring={
            "metric_caps": {"psi": 0.5},
            "metric_weights": {"psi": 1.0},
            "train_calibration": False,
        }
    )
    scored = _score(_metric_rows([0.25, 0.5, 5.0]), policy)
    assert list(scored["drift_score"].round(3)) == [0.5, 1.0, 1.0]  # capped at 1
    payload = json.loads(scored["metric_scores"].iloc[0])
    assert payload["psi"]["norm"] == 0.5


def test_train_calibration_subtracts_train_envelope(
    policy_factory: Callable[..., DriftPolicy],
) -> None:
    policy = policy_factory(
        scoring={
            "metric_caps": {"psi": 1.0},
            "metric_weights": {"psi": 1.0},
            "train_calibration": True,
            "train_calibration_quantile": 1.0,
            "train_calibration_min_windows": 3,
            "excess_cap": 0.2,
            "persistence_bonus": 0.0,
        }
    )
    # 4 train windows up to 0.4; validation windows at 0.4 (in-envelope) / 0.6.
    rows = _metric_rows([0.2, 0.3, 0.4, 0.35, 0.4, 0.6])
    scored = _score(rows, policy, train_end="2024-06-01 04:00")
    assert scored["is_train_window"].tolist() == [True] * 4 + [False] * 2
    assert scored["drift_score"].iloc[4] == 0.0  # within the train envelope
    assert scored["drift_score"].iloc[5] == pytest.approx(1.0)  # 0.2 / 0.2 cap
    assert scored["uncalibrated_score"].iloc[5] == 0.6  # transparency kept


def test_persistence_bonus_applies_after_consecutive_active_windows(
    policy_factory: Callable[..., DriftPolicy],
) -> None:
    policy = policy_factory(
        scoring={
            "metric_caps": {"psi": 1.0},
            "metric_weights": {"psi": 1.0},
            "train_calibration": False,
            "persistence_bonus": 0.1,
            "persistence_min_windows": 2,
        }
    )
    scored = _score(_metric_rows([0.6, 0.6, 0.3]), policy)
    assert scored["drift_score"].iloc[0] == 0.6  # run too short
    assert scored["drift_score"].iloc[1] == 0.7  # second consecutive active
    assert scored["drift_score"].iloc[2] == 0.3


def test_sensor_health_override_reclassifies_only_overlapping_sensor_windows(
    policy_factory: Callable[..., DriftPolicy],
) -> None:
    policy = policy_factory(scoring={"train_calibration": False})
    rows = pd.concat(
        [
            _metric_rows([0.6] * 4, entity="bad"),
            _metric_rows([0.6] * 4, entity="fine"),
        ],
        ignore_index=True,
    )
    scored = _score(rows, policy)
    events = pd.DataFrame(
        [
            {
                "sensor": "bad",
                "issue_types": "flatline_zero",
                "start_timestamp": pd.Timestamp("2024-06-01 02:00"),
                "end_timestamp": pd.Timestamp("2024-06-01 23:00"),
            }
        ]
    )
    out = scoring.apply_sensor_health_override(scored, events, policy)
    bad = out[out.entity == "bad"].sort_values("window_start")
    assert list(bad["drift_type"]) == ["process_drift"] * 2 + ["sensor_drift"] * 2
    assert (out[out.entity == "fine"]["drift_type"] == "process_drift").all()
    # severity is never reduced by the override
    assert (out["drift_score"] == scored["drift_score"]).all()


def _scored(
    values: list[float],
    policy: DriftPolicy,
    *,
    entity: str = "s1",
    scope: str = "sensor",
    view: str = "raw",
) -> pd.DataFrame:
    rows = _metric_rows(values, entity=entity, scope=scope, view=view)
    inner = policy.model_copy(deep=True)
    inner.scoring.train_calibration = False
    inner.scoring.persistence_bonus = 0.0
    return scoring.normalize_and_score(rows, inner, _HOUR, pd.Timestamp("1970-01-01"))


def _events(values: list[float], policy: DriftPolicy, **kwargs: str) -> pd.DataFrame:
    scored = _scored(values, policy, **kwargs)
    last = scored["window_start"].max()
    return events_mod.extract_events(scored, policy, last)


def test_event_shapes_and_statuses(
    policy_factory: Callable[..., DriftPolicy],
) -> None:
    policy = policy_factory(
        scoring={"metric_caps": {"psi": 1.0}, "metric_weights": {"psi": 1.0}},
        events={
            "active_score_threshold": 0.5,
            "gap_merge_windows": 1,
            "candidate_max_windows": 1,
            "persistent_min_windows": 4,
            "abrupt_onset_max_windows": 1,
            "progressive_min_onset_windows": 3,
            "episodic_min_segments": 3,
        },
    )
    # Abrupt + persistent + touches end -> abrupt shape, persistent status.
    ev = _events([0.1, 0.9, 0.9, 0.9, 0.9, 0.9], policy)
    assert len(ev) == 1
    assert ev.iloc[0]["temporal_shape"] == "abrupt"
    assert ev.iloc[0]["status"] == "persistent"
    assert bool(ev.iloc[0]["is_persistent"])
    assert ev.iloc[0]["review_status"] == "pending_review"

    # Short resolved burst -> transient.
    ev = _events([0.1, 0.6, 0.7, 0.1, 0.1, 0.1, 0.1], policy)
    assert ev.iloc[0]["temporal_shape"] == "transient"
    assert ev.iloc[0]["status"] == "resolved"

    # Single active window -> candidate.
    ev = _events([0.1, 0.6, 0.1, 0.1, 0.1], policy)
    assert ev.iloc[0]["status"] == "candidate"

    # Progressive ramp: slow monotone onset to the peak.
    ev = _events([0.55, 0.6, 0.7, 0.8, 0.95, 0.95], policy)
    assert ev.iloc[0]["temporal_shape"] == "progressive"

    # Episodic: >= 3 active runs merged across 1-window gaps.
    ev = _events([0.6, 0.1, 0.6, 0.1, 0.6, 0.1, 0.6], policy)
    assert len(ev) == 1
    assert ev.iloc[0]["temporal_shape"] == "episodic"

    # Gap larger than gap_merge_windows splits events.
    ev = _events([0.6, 0.6, 0.1, 0.1, 0.1, 0.6, 0.6], policy)
    assert len(ev) == 2


def test_promoted_events_and_absorption(
    policy_factory: Callable[..., DriftPolicy],
) -> None:
    policy = policy_factory(
        scoring={"metric_caps": {"psi": 1.0}, "metric_weights": {"psi": 1.0}},
        events={"promoted_event_absorb_coverage": 0.7},
    )
    sh_events = pd.DataFrame(
        [
            {
                "sensor_health_event_id": "SH-bad-1",
                "sensor": "bad",
                "start_timestamp": pd.Timestamp("2024-06-01 01:30:15"),
                "end_timestamp": pd.Timestamp("2024-06-01 06:00:00"),
                "status": "faulty",
                "issue_types": "flatline_zero",
                "max_health_score": 0.95,
                "affected_profiles": "mid_production",
                "is_persistent": True,
            },
            {
                "sensor_health_event_id": "SH-blip-2",
                "sensor": "blip",
                "start_timestamp": pd.Timestamp("2024-06-01 02:00"),
                "end_timestamp": pd.Timestamp("2024-06-01 02:30"),
                "status": "faulty",
                "issue_types": "missingness_spike",
                "max_health_score": 0.7,
                "affected_profiles": "stopped",
                "is_persistent": False,
            },
            {
                "sensor_health_event_id": "SH-warn-3",
                "sensor": "warned",
                "start_timestamp": pd.Timestamp("2024-06-01 02:00"),
                "end_timestamp": pd.Timestamp("2024-06-01 03:00"),
                "status": "warning",  # warnings are never promoted
                "issue_types": "abrupt_offset",
                "max_health_score": 0.4,
                "affected_profiles": "stopped",
                "is_persistent": False,
            },
        ]
    )
    promoted = events_mod.promote_sensor_health_events(sh_events, policy)
    assert set(promoted["affected_sensors"]) == {"bad", "blip"}
    bad = promoted[promoted["affected_sensors"] == "bad"].iloc[0]
    assert bad["drift_type"] == "sensor_drift"
    assert bad["temporal_shape"] == "abrupt"
    assert bad["status"] == "persistent"
    assert bad["severity"] == "critical"
    blip = promoted[promoted["affected_sensors"] == "blip"].iloc[0]
    assert blip["temporal_shape"] == "transient"
    assert blip["status"] == "resolved"

    window_events = _events([0.1, 0.1, 0.9, 0.9, 0.9, 0.1], policy, entity="bad")
    merged = events_mod.merge_promoted(window_events, promoted, policy)
    bad_events = merged[merged["affected_sensors"] == "bad"]
    assert len(bad_events) == 1  # absorbed into the promoted event
    survivor = bad_events.iloc[0]
    # Precise instrumentation timing is the authority, never widened.
    assert survivor["start_timestamp"] == pd.Timestamp("2024-06-01 01:30:15")
    evidence = json.loads(survivor["evidence"])
    assert evidence["absorbed_event_ids"] == [window_events.iloc[0]["drift_event_id"]]


def test_dominance_filter_excludes_dominated_but_exempts_proxy(
    policy_factory: Callable[..., DriftPolicy],
) -> None:
    policy = policy_factory(healthy_view={"evidence_dominance_fraction": 0.6})
    dominated = _events(
        [0.1, 0.9, 0.9, 0.9],
        policy,
        entity="combined_score",
        scope="multivariate",
        view="healthy_only",
    )
    raw_twin = _events(
        [0.1, 0.9, 0.9, 0.9],
        policy,
        entity="combined_score",
        scope="multivariate",
        view="raw",
    )
    proxy = _events(
        [0.1, 0.9, 0.9, 0.9],
        policy,
        entity="q_spe_healthy_only_proxy",
        scope="multivariate",
        view="healthy_only",
    )
    events = pd.concat([dominated, raw_twin, proxy], ignore_index=True)
    windows = pd.date_range("2024-06-01", periods=4, freq="1h")
    dominance = pd.Series(1.0, index=windows)
    kept, excluded = events_mod.filter_dominated_events(events, dominance, policy)
    assert len(excluded) == 1
    assert excluded.iloc[0]["view"] == "healthy_only"
    assert "proxy" not in excluded.iloc[0]["drift_event_id"]
    kept_ids = set(kept["drift_event_id"])
    assert any("proxy" in i for i in kept_ids)  # Level-B proxy survives
    assert any(i for i in kept_ids if "proxy" not in i)  # raw twin survives untouched


def test_correlation_events_only_from_material_process_breaks(
    policy_factory: Callable[..., DriftPolicy],
) -> None:
    policy = policy_factory(correlation={"min_material_pairs_for_event": 2})
    classified = pd.DataFrame(
        [
            {
                "profile": "mid_production",
                "feature_a": f"a{i}",
                "feature_b": f"b{i}",
                "pearson_train": 0.9,
                "pearson_validation": 0.1,
                "abs_delta": 0.8,
                "spearman_train": 0.9,
                "change_class": "collapsed",
                "classification": classification,
                "dominant_sensor": "",
                "evidence": "{}",
            }
            for i, classification in enumerate(
                [
                    "process_correlation_break",
                    "process_correlation_break",
                    "sensor_drift_evidence",
                ]
            )
        ]
    )
    start, end = pd.Timestamp("2024-09-03"), pd.Timestamp("2024-10-08")
    events = events_mod.correlation_events(classified, start, end, policy)
    assert len(events) == 1
    event = events.iloc[0]
    assert event["drift_type"] == "correlation_shift"
    assert event["scope"] == "correlation"
    assert event["start_timestamp"] == start
    # sensor_drift_evidence pairs never create process events
    assert "a2" not in event["affected_sensors"]
