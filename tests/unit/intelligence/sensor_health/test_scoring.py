"""Scoring: health_score formula, the three faulty paths, unknown handling."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from src.intelligence.sensor_health.policy import SensorHealthPolicy
from src.intelligence.sensor_health.rules import RuleReferences, RuleResult
from src.intelligence.sensor_health.scoring import (
    quality_timeline,
    score_sensor,
)


def _result(issue: str, mask: np.ndarray, strength: float = 1.0) -> RuleResult:
    return RuleResult(issue, mask, np.where(mask, strength, 0.0))


def _refs(zero_fraction: float = 0.5) -> RuleReferences:
    refs = RuleReferences()
    refs.train_zero_fraction["s1"] = zero_fraction
    return refs


def test_score_is_max_plus_corroboration() -> None:
    n = 10
    values = np.full(n, 5.0)
    m1 = np.zeros(n, dtype=bool)
    m1[:4] = True
    m2 = np.zeros(n, dtype=bool)
    m2[:2] = True
    policy = SensorHealthPolicy()
    s = score_sensor(
        "s1",
        values,
        [_result("flatline", m1), _result("stale_signal", m2)],
        _refs(),
        policy,
    )
    assert s.score[3] == 0.7  # single family: base x strength
    assert s.score[1] == 0.8  # two families: max + 0.1 bonus
    assert s.score[5] == 0.0


def test_faulty_via_persistent_strong_rule() -> None:
    n = 200
    mask = np.zeros(n, dtype=bool)
    mask[:130] = True  # >= persistent_min_rows (120)
    s = score_sensor(
        "s1",
        np.full(n, 5.0),
        [_result("flatline", mask)],
        _refs(),
        SensorHealthPolicy(),
    )
    assert (s.status[:130] == "faulty").all()
    assert (s.status[130:] == "healthy").all()


def test_faulty_via_corroborating_families() -> None:
    n = 50
    mask = np.zeros(n, dtype=bool)
    mask[:10] = True
    s = score_sensor(
        "s1",
        np.full(n, 5.0),
        [_result("flatline", mask), _result("missingness_spike", mask)],
        _refs(),
        SensorHealthPolicy(),
    )
    assert (s.status[:10] == "faulty").all()  # 2 families, score 0.8 >= 0.7


def test_faulty_via_flatline_zero_on_abnormal_sensor() -> None:
    n = 50
    mask = np.zeros(n, dtype=bool)
    mask[:20] = True  # short, not persistent
    s = score_sensor(
        "s1",
        np.full(n, 0.0),
        [_result("flatline_zero", mask)],
        _refs(zero_fraction=0.0),  # zero is abnormal in train
        SensorHealthPolicy(),
    )
    assert (s.status[:20] == "faulty").all()


def test_single_weak_rule_stays_warning() -> None:
    n = 300
    mask = np.zeros(n, dtype=bool)
    mask[:250] = True  # persistent but weak (abrupt_offset base 0.4)
    s = score_sensor(
        "s1",
        np.full(n, 5.0),
        [_result("abrupt_offset", mask, strength=0.6)],
        _refs(),
        SensorHealthPolicy(),
    )
    assert (s.status[:250] == "warning").all()


def test_unknown_on_missing_values_without_rules() -> None:
    values = np.full(100, np.nan)
    s = score_sensor("s1", values, [], _refs(), SensorHealthPolicy())
    assert (s.status == "unknown").all()


def test_evidence_only_on_flagged_rows() -> None:
    n = 20
    mask = np.zeros(n, dtype=bool)
    mask[3] = True
    s = score_sensor(
        "s1",
        np.full(n, 5.0),
        [_result("flatline", mask)],
        _refs(),
        SensorHealthPolicy(),
    )
    assert s.evidence[3] != "" and json.loads(s.evidence[3])["flatline"] == 1.0
    assert s.issue_types[3] == "flatline"
    assert (s.evidence[np.arange(n) != 3] == "").all()


def test_counter_substate_changes_base_and_token() -> None:
    n = 10
    mask = np.ones(n, dtype=bool)
    sub = np.full(n, "recovered_after_reset", dtype=object)
    result = RuleResult("counter_reset", mask, np.ones(n), substates=sub)
    s = score_sensor("s1", np.full(n, 5.0), [result], _refs(), SensorHealthPolicy())
    assert s.score[0] == 0.4  # counter_reset_recovered base
    assert s.issue_types[0] == "counter_reset:recovered_after_reset"


def test_quality_timeline_priority_and_lists() -> None:
    ts = pd.date_range("2024-09-01", periods=4, freq="1min")
    mk = lambda statuses: type(  # noqa: E731
        "S", (), {"status": np.array(statuses, object)}
    )()
    per_sensor = {
        "a": mk(["healthy", "warning", "faulty", "unknown"]),
        "b": mk(["healthy", "healthy", "warning", "unknown"]),
    }
    tl = quality_timeline(ts, per_sensor, {})
    assert list(tl["sensor_health_context"]) == [
        "all_sensors_healthy",
        "sensor_warning",
        "sensor_faulty",
        "unknown",
    ]
    assert tl.loc[2, "faulty_sensors"] == "a"
    assert tl.loc[2, "warning_sensors"] == "b"
    assert tl.loc[3, "unknown_sensors"] == "a|b"
    assert list(tl["n_sensors_evaluated"]) == [2, 2, 2, 0]
