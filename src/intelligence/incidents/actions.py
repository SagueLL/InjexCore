"""Recommended actions per incident — guidance, never execution.

Quarantine-class actions always carry ``approval_required=True`` and
``approved=False`` (hardcoded, mirroring the sensor-health discipline): this
component never excludes a sensor from production scoring and never approves
a quarantine recommendation.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from src.intelligence.incidents.policy import IncidentsPolicy

ACTION_COLUMNS = [
    "incident_id",
    "recommended_action",
    "reason",
    "priority",
    "approval_required",
    "approved",
]

QUARANTINE_ACTION = "quarantine_from_process_scoring"

_PRIORITY = {"critical": "high", "anomaly": "high", "warning": "medium", "info": "low"}


def recommend(incidents: pd.DataFrame, policy: IncidentsPolicy) -> pd.DataFrame:
    """One row per (incident, action); deterministic order."""
    if not len(incidents):
        return pd.DataFrame(columns=ACTION_COLUMNS)
    rows: list[dict[str, Any]] = []
    for _, incident in incidents.iterrows():
        for action in _actions_for(incident, policy):
            quarantine = action == QUARANTINE_ACTION
            rows.append(
                {
                    "incident_id": str(incident["incident_id"]),
                    "recommended_action": action,
                    "reason": _reason(incident, action),
                    "priority": _PRIORITY.get(str(incident["severity"]), "low"),
                    # Quarantine is a recommendation requiring human approval —
                    # never auto-approved, never auto-applied.
                    "approval_required": quarantine,
                    "approved": False,
                }
            )
    return pd.DataFrame(rows, columns=ACTION_COLUMNS)


def _actions_for(incident: pd.Series, policy: IncidentsPolicy) -> list[str]:
    incident_type = str(incident["incident_type"])
    actions = list(policy.actions.by_type.get(incident_type, ["review_operator_notes"]))
    evidence = str(incident["evidence"])
    if incident_type in ("sensor_fault", "sensor_warning") and "counter_reset" in (
        evidence
    ):
        actions.append(policy.actions.counter_reset_action)
    if (
        incident_type == "sensor_fault"
        and policy.actions.quarantine_for_persistent_critical_sensor_fault
        and bool(incident["is_persistent"])
        and str(incident["severity"]) == "critical"
    ):
        actions.append(QUARANTINE_ACTION)
    return list(dict.fromkeys(actions))  # dedupe, keep order


def _reason(incident: pd.Series, action: str) -> str:
    payload = {
        "incident_type": str(incident["incident_type"]),
        "severity": str(incident["severity"]),
        "status": str(incident["status"]),
        "affected_sensors": str(incident["affected_sensors"]),
    }
    if action == QUARANTINE_ACTION:
        payload["basis"] = "persistent_critical_sensor_fault"
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))
