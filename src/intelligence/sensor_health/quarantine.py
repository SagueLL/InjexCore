"""Quarantine recommendation policy — recommendation only, never exclusion.

Sensor Health Intelligence recommends quarantine; it does not modify model
inputs automatically. Every recommendation carries ``approval_required=True``
and ``approved=False`` (hardcoded) — promotion into actual scoring scope is
a human decision tracked outside this component.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.intelligence.sensor_health.policy import SensorHealthPolicy

QUARANTINE_COLUMNS = [
    "sensor",
    "start_timestamp",
    "end_timestamp",
    "reason",
    "issue_types",
    "severity",
    "recommended_action",
    "approval_required",
    "approved",
]


def _families(issue_types: str) -> set[str]:
    return {t.split(":")[0] for t in issue_types.split("|") if t}


def triggering_events(events: pd.DataFrame, policy: SensorHealthPolicy) -> pd.DataFrame:
    """Events that satisfy the quarantine trigger conditions."""
    if events.empty:
        return events
    triggers = set(policy.quarantine.trigger_issue_types)
    mask = events["status"] == "faulty"
    if policy.quarantine.require_persistent:
        mask &= events["is_persistent"]
    mask &= events["issue_types"].map(lambda t: bool(_families(t) & triggers))
    return events[mask]


def build_recommendations(
    events: pd.DataFrame, policy: SensorHealthPolicy
) -> pd.DataFrame:
    """One recommendation row per sensor with triggering events."""
    triggering = triggering_events(events, policy)
    rows: list[dict[str, Any]] = []
    if not triggering.empty:
        for sensor, group in triggering.groupby("sensor", sort=True):
            issue_union = "|".join(
                sorted({t for it in group["issue_types"] for t in it.split("|") if t})
            )
            rows.append(
                {
                    "sensor": sensor,
                    "start_timestamp": group["start_timestamp"].min(),
                    "end_timestamp": group["end_timestamp"].max(),
                    "reason": (
                        f"{len(group)} persistent faulty event(s) with "
                        f"quarantine-trigger issues [{issue_union}]; "
                        "recommend excluding this sensor from process scoring "
                        "pending review"
                    ),
                    "issue_types": issue_union,
                    "severity": "faulty",
                    "recommended_action": "quarantine_from_process_scoring",
                    "approval_required": True,  # hardcoded by design
                    "approved": False,  # hardcoded by design
                }
            )
    return pd.DataFrame(rows, columns=QUARANTINE_COLUMNS)


def flag_rows(
    events: pd.DataFrame,
    policy: SensorHealthPolicy,
    timestamps: pd.Index,
) -> dict[str, np.ndarray]:
    """Per-sensor boolean arrays: rows inside a triggering event's span."""
    flags: dict[str, np.ndarray] = {}
    ts = timestamps.to_numpy()
    for event in triggering_events(events, policy).itertuples(index=False):
        arr = flags.setdefault(event.sensor, np.zeros(len(ts), dtype=bool))
        inside = (ts >= np.datetime64(event.start_timestamp)) & (
            ts <= np.datetime64(event.end_timestamp)
        )
        arr |= inside
    return flags
