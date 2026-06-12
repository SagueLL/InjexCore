"""Event aggregation + quarantine recommendation policy."""

from __future__ import annotations

import numpy as np
import pandas as pd
from src.intelligence.sensor_health.events import extract_events
from src.intelligence.sensor_health.policy import SensorHealthPolicy
from src.intelligence.sensor_health.quarantine import (
    build_recommendations,
    flag_rows,
)
from src.intelligence.sensor_health.scoring import SensorScore


def _sensor_score(
    n: int,
    flagged: list[tuple[int, int, str]],
    issue: str = "flatline_zero",
) -> SensorScore:
    status = np.full(n, "healthy", dtype=object)
    score = np.zeros(n)
    tokens = np.full(n, "", dtype=object)
    for i, j, st in flagged:
        status[i:j] = st
        score[i:j] = 0.9
        tokens[i:j] = issue
    return SensorScore("s1", status, score, tokens, np.full(n, "", dtype=object))


def _world(n: int, flagged: list[tuple[int, int, str]], **policy: dict):
    ts = pd.date_range("2024-09-01", periods=n, freq="1min")
    profiles = np.array(["run"] * n, dtype=object)
    pol = SensorHealthPolicy.model_validate(policy)
    per_sensor = {"s1": _sensor_score(n, flagged)}
    events = extract_events(ts, profiles, per_sensor, pol)
    return ts, pol, events


def test_gap_merge_joins_one_physical_episode() -> None:
    _, _, events = _world(
        100, [(10, 30, "faulty"), (33, 50, "faulty")], events={"gap_merge_rows": 5}
    )
    assert len(events) == 1
    assert events.loc[0, "duration_rows"] == 40
    _, _, separate = _world(
        100, [(10, 30, "faulty"), (40, 50, "faulty")], events={"gap_merge_rows": 5}
    )
    assert len(separate) == 2


def test_event_fields_and_deterministic_id() -> None:
    ts, _, events = _world(100, [(10, 30, "faulty")])
    row = events.iloc[0]
    assert row["sensor_health_event_id"] == "SH-s1-20240901T001000Z"
    assert row["status"] == "faulty"
    assert row["issue_types"] == "flatline_zero"
    assert row["review_status"] == "pending_review"
    assert row["start_timestamp"] == ts[10]
    assert row["end_timestamp"] == ts[29]
    assert bool(row["is_persistent"]) is False


def test_persistence_threshold() -> None:
    _, _, events = _world(
        400, [(10, 300, "faulty")], events={"persistent_event_rows": 240}
    )
    assert bool(events.loc[0, "is_persistent"]) is True
    assert events.loc[0, "recommended_action"] == "quarantine_recommended"


def test_quarantine_trigger_and_constants() -> None:
    _, pol, events = _world(
        400, [(10, 300, "faulty")], events={"persistent_event_rows": 240}
    )
    recs = build_recommendations(events, pol)
    assert len(recs) == 1
    rec = recs.iloc[0]
    assert rec["sensor"] == "s1"
    assert rec["recommended_action"] == "quarantine_from_process_scoring"
    assert bool(rec["approval_required"]) is True
    assert bool(rec["approved"]) is False


def test_no_quarantine_for_warning_or_non_persistent_or_non_trigger() -> None:
    _, pol, warning = _world(400, [(10, 300, "warning")])
    assert build_recommendations(warning, pol).empty
    _, pol, short = _world(400, [(10, 60, "faulty")])
    assert build_recommendations(short, pol).empty
    ts = pd.date_range("2024-09-01", periods=400, freq="1min")
    profiles = np.array(["run"] * 400, dtype=object)
    pol2 = SensorHealthPolicy()
    per = {"s1": _sensor_score(400, [(10, 300, "faulty")], issue="variance_collapse")}
    events = extract_events(ts, profiles, per, pol2)
    assert build_recommendations(events, pol2).empty  # not a trigger issue


def test_flag_rows_marks_triggering_event_span() -> None:
    ts, pol, events = _world(
        400, [(10, 300, "faulty")], events={"persistent_event_rows": 240}
    )
    flags = flag_rows(events, pol, ts)
    assert flags["s1"][10:300].all()
    assert not flags["s1"][:10].any()
    assert not flags["s1"][300:].any()


def test_recommended_action_vocabulary() -> None:
    _, _, offset = _world(
        100,
        [(10, 30, "warning")],
    )
    # craft via issue tokens
    ts = pd.date_range("2024-09-01", periods=100, freq="1min")
    profiles = np.array(["run"] * 100, dtype=object)
    pol = SensorHealthPolicy()
    per = {"s1": _sensor_score(100, [(10, 30, "warning")], issue="abrupt_offset")}
    ev = extract_events(ts, profiles, per, pol)
    assert ev.loc[0, "recommended_action"] == "verify_calibration"
    per = {"s1": _sensor_score(100, [(10, 30, "warning")], issue="missingness_spike")}
    ev = extract_events(ts, profiles, per, pol)
    assert ev.loc[0, "recommended_action"] == "review_data_pipeline"
    per = {"s1": _sensor_score(100, [(10, 30, "faulty")], issue="variance_collapse")}
    ev = extract_events(ts, profiles, per, pol)
    assert ev.loc[0, "recommended_action"] == "inspect_sensor"
