"""Event aggregation — row-level verdicts become reviewable episodes.

Consecutive flagged rows (status warning/faulty) per sensor are grouped into
events; short healthy gaps are merged so one physical episode stays one
event. Every new event defaults to ``review_status = "pending_review"`` —
nothing is auto-confirmed.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from src.intelligence.sensor_health.policy import SensorHealthPolicy
from src.intelligence.sensor_health.rules import run_segments
from src.intelligence.sensor_health.scoring import SensorScore

EVENT_COLUMNS = [
    "sensor_health_event_id",
    "sensor",
    "start_timestamp",
    "end_timestamp",
    "duration_rows",
    "duration_seconds",
    "status",
    "issue_types",
    "max_health_score",
    "affected_profiles",
    "evidence",
    "recommended_action",
    "is_persistent",
    "review_status",
]

REVIEW_STATUSES = ("pending_review", "confirmed", "dismissed", "resolved")


def _merged_segments(flagged: np.ndarray, gap_merge_rows: int) -> list[tuple[int, int]]:
    """Flagged runs with gaps of ``<= gap_merge_rows`` healthy rows merged."""
    segments = run_segments(flagged)
    if not segments:
        return []
    merged = [segments[0]]
    for i, j in segments[1:]:
        last_i, last_j = merged[-1]
        if i - last_j <= gap_merge_rows:
            merged[-1] = (last_i, j)
        else:
            merged.append((i, j))
    return merged


def _issue_union(tokens: np.ndarray) -> str:
    out: set[str] = set()
    for t in tokens:
        if t:
            out.update(t.split("|"))
    return "|".join(sorted(out))


def recommended_action(
    issue_types: str, status: str, is_persistent: bool, policy: SensorHealthPolicy
) -> str:
    """Priority-ordered review guidance for one event."""
    families = {t.split(":")[0] for t in issue_types.split("|") if t}
    triggers = set(policy.quarantine.trigger_issue_types)
    if status == "faulty" and is_persistent and families & triggers:
        return "quarantine_recommended"
    if status == "faulty":
        return "inspect_sensor"
    if families == {"abrupt_offset"}:
        return "verify_calibration"
    if "missingness_spike" in families:
        return "review_data_pipeline"
    return "monitor"


def extract_events(
    timestamps: pd.Index,
    profiles: np.ndarray,
    per_sensor: dict[str, SensorScore],
    policy: SensorHealthPolicy,
) -> pd.DataFrame:
    """One row per merged warning/faulty episode, ``pending_review``."""
    ts = timestamps.to_numpy()
    rows: list[dict[str, Any]] = []
    for sensor in sorted(per_sensor):
        s = per_sensor[sensor]
        flagged = np.isin(s.status, ("warning", "faulty"))
        for i, j in _merged_segments(flagged, policy.events.gap_merge_rows):
            rows.append(_event_row(sensor, i, j, ts, profiles, s, policy))
    return pd.DataFrame(rows, columns=EVENT_COLUMNS)


def _event_row(
    sensor: str,
    i: int,
    j: int,
    ts: np.ndarray,
    profiles: np.ndarray,
    s: SensorScore,
    policy: SensorHealthPolicy,
) -> dict[str, Any]:
    start = pd.Timestamp(ts[i])
    end = pd.Timestamp(ts[j - 1])
    duration_rows = j - i
    status = "faulty" if (s.status[i:j] == "faulty").any() else "warning"
    issue_types = _issue_union(s.issue_types[i:j])
    is_persistent = duration_rows >= policy.events.persistent_event_rows
    peak: dict[str, float] = {}
    for tokens, score in zip(s.issue_types[i:j], s.score[i:j], strict=True):
        for t in tokens.split("|") if tokens else []:
            peak[t] = max(peak.get(t, 0.0), float(score))
    return {
        "sensor_health_event_id": f"SH-{sensor}-{start.strftime('%Y%m%dT%H%M%SZ')}",
        "sensor": sensor,
        "start_timestamp": start,
        "end_timestamp": end,
        "duration_rows": duration_rows,
        "duration_seconds": float((end - start).total_seconds()),
        "status": status,
        "issue_types": issue_types,
        "max_health_score": float(s.score[i:j].max()),
        "affected_profiles": "|".join(sorted({str(p) for p in profiles[i:j]})),
        "evidence": json.dumps(
            {"rows": duration_rows, "peak_score_by_issue": peak},
            sort_keys=True,
            separators=(",", ":"),
        ),
        "recommended_action": recommended_action(
            issue_types, status, is_persistent, policy
        ),
        "is_persistent": is_persistent,
        "review_status": "pending_review",
    }
