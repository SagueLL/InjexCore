"""Quarantine + candidate-reference proposal construction.

Turns persisted sensor-health / incident / drift evidence into reviewable
proposals. Every proposal is ``pending_review`` with ``approved=False``: this
module proposes and never approves, never excludes a sensor and never refits
a model. Candidate train windows are left null — they are never fabricated
from data the layer cannot justify.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import pandas as pd

QUARANTINE_PROPOSAL_COLUMNS = [
    "quarantine_proposal_id",
    "sensor",
    "start_timestamp",
    "end_timestamp",
    "status",
    "reason",
    "source_incident_ids",
    "source_sensor_health_event_ids",
    "source_drift_event_ids",
    "recommended_action",
    "approval_required",
    "approved",
    "risk_if_ignored",
    "risk_if_applied",
    "expected_effect",
    "review_status",
]

PROPOSAL_COLUMNS = [
    "proposal_id",
    "proposal_type",
    "status",
    "created_at",
    "based_on_reference_id",
    "candidate_reference_id",
    "proposed_train_start",
    "proposed_train_end",
    "context_scope",
    "sensor_scope",
    "excluded_sensors",
    "model_refit_required",
    "approval_required",
    "source_incident_ids",
    "source_drift_event_ids",
    "evidence_summary",
    "risk_summary",
    "required_human_records",
    "recommended_next_step",
]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _pipe(values: list[str]) -> str:
    """Stable, de-duplicated pipe-joined string (the repo's multi-value idiom)."""
    seen: list[str] = []
    for v in values:
        if v and v not in seen:
            seen.append(v)
    return "|".join(seen)


def _ts_token(ts: Any) -> str:
    stamp = pd.Timestamp(ts)
    return "unknown" if pd.isna(stamp) else stamp.strftime("%Y%m%dT%H%M%SZ")


def _contains_token(series: pd.Series, token: str) -> pd.Series:
    """Pipe-boundary membership test over a pipe-joined string column."""
    pattern = rf"(?:^|\|){re.escape(token)}(?:\||$)"
    return series.fillna("").astype(str).str.contains(pattern, regex=True)


def _sensor_incident_ids(sensor: str, incidents: pd.DataFrame) -> list[str]:
    if not len(incidents):
        return []
    mask = _contains_token(incidents["affected_sensors"], sensor) & incidents[
        "incident_type"
    ].isin(["sensor_fault", "sensor_warning"])
    return incidents.loc[mask, "incident_id"].astype(str).tolist()


def _sensor_drift_ids(sensor: str, drift_events: pd.DataFrame) -> list[str]:
    if not len(drift_events):
        return []
    mask = _contains_token(drift_events["affected_sensors"], sensor) & (
        drift_events["drift_type"] == "sensor_drift"
    )
    return drift_events.loc[mask, "drift_event_id"].astype(str).tolist()


def _sensor_health_event_ids(sensor: str, sh_events: pd.DataFrame) -> list[str]:
    if not len(sh_events):
        return []
    mask = (sh_events["sensor"] == sensor) & (sh_events["status"] == "faulty")
    return sh_events.loc[mask, "sensor_health_event_id"].astype(str).tolist()


def build_quarantine_proposals(
    recommendations: pd.DataFrame,
    sh_events: pd.DataFrame,
    incidents: pd.DataFrame,
    drift_events: pd.DataFrame,
    candidate_sensors: list[str],
) -> pd.DataFrame:
    """One pending quarantine proposal per recommended (allow-listed) sensor."""
    allow = set(candidate_sensors)
    rows: list[dict[str, Any]] = []
    for rec in recommendations.itertuples(index=False):
        sensor = str(rec.sensor)
        if allow and sensor not in allow:
            continue
        rows.append(
            {
                "quarantine_proposal_id": f"QP-{sensor}-{_ts_token(rec.start_timestamp)}",
                "sensor": sensor,
                "start_timestamp": rec.start_timestamp,
                "end_timestamp": rec.end_timestamp,
                "status": "pending_review",
                "reason": str(rec.reason),
                "source_incident_ids": _pipe(_sensor_incident_ids(sensor, incidents)),
                "source_sensor_health_event_ids": _pipe(
                    _sensor_health_event_ids(sensor, sh_events)
                ),
                "source_drift_event_ids": _pipe(
                    _sensor_drift_ids(sensor, drift_events)
                ),
                "recommended_action": str(rec.recommended_action),
                "approval_required": True,
                "approved": False,
                "risk_if_ignored": (
                    "A known instrumentation fault keeps dominating process "
                    "scoring, masking or inflating genuine process anomalies."
                ),
                "risk_if_applied": (
                    "A real process signal co-located with the faulty channel "
                    "could be hidden; mitigated because this quarantine is "
                    "interpretive and reversible (no model refit)."
                ),
                "expected_effect": (
                    "Removes instrumentation-dominated anomaly evidence from "
                    "process scoring; magnitude quantified by the controlled "
                    "scoring experiment."
                ),
                "review_status": "pending_review",
            }
        )
    return pd.DataFrame(rows, columns=QUARANTINE_PROPOSAL_COLUMNS)


def residual_diagnostic(
    raw_vs_healthy: pd.DataFrame, residual_window_min: int, residual_fraction_min: float
) -> dict[str, Any]:
    """Materiality of residual healthy-only sensor drift (sensor scope only)."""
    sensor = (
        raw_vs_healthy[raw_vs_healthy["scope"] == "sensor"]
        if len(raw_vs_healthy)
        else raw_vs_healthy
    )
    n_windows = int(len(sensor))
    raw_mass = float(sensor["drift_score_raw"].fillna(0.0).sum()) if n_windows else 0.0
    healthy_mass = (
        float(sensor["drift_score_healthy_only"].fillna(0.0).sum())
        if n_windows
        else 0.0
    )
    n_residual = int(sensor["residual_drift"].sum()) if n_windows else 0
    fraction = n_residual / n_windows if n_windows else 0.0
    reduction = (raw_mass - healthy_mass) / raw_mass * 100.0 if raw_mass > 0 else 0.0
    material = n_residual >= residual_window_min and fraction >= residual_fraction_min
    return {
        "n_windows": n_windows,
        "n_residual_windows": n_residual,
        "residual_fraction": fraction,
        "raw_mass": raw_mass,
        "healthy_mass": healthy_mass,
        "reduction_pct": reduction,
        "material": bool(material),
    }


def _quarantine_only_proposal(
    excluded: str, incident_ids: str, drift_ids: str
) -> dict[str, Any]:
    return {
        "proposal_id": "RP-quarantine_only",
        "proposal_type": "quarantine_only",
        "status": "pending_review",
        "created_at": _now(),
        "based_on_reference_id": "reference_v1",
        "candidate_reference_id": "",
        "proposed_train_start": "",
        "proposed_train_end": "",
        "context_scope": "none",
        "sensor_scope": "all_supported_minus_excluded",
        "excluded_sensors": excluded,
        "model_refit_required": False,
        "approval_required": True,
        "source_incident_ids": incident_ids,
        "source_drift_event_ids": drift_ids,
        "evidence_summary": (
            "Persistent critical sensor_fault on the excluded channel(s). "
            "Evaluate whether this instrumentation fault explains the anomaly "
            "mass without changing the reference or refitting any model."
        ),
        "risk_summary": (
            "Interpretive only; no reference change, no refit. The controlled "
            "scoring experiment quantifies the impact before any approval."
        ),
        "required_human_records": "",
        "recommended_next_step": (
            "Run the controlled scoring experiment to quantify the interpretive "
            "impact, then route the quarantine proposal for human approval."
        ),
    }


def _candidate_v2_proposal(
    excluded: str, residual: dict[str, Any], incident_ids: str, drift_ids: str
) -> dict[str, Any]:
    material = bool(residual["material"])
    next_step = (
        "Design Reference v2 after plant-record review confirms the residual is "
        "a genuine process change."
        if material
        else "Defer Reference v2: residual healthy-only drift is below the "
        "materiality threshold; inspect the channel and collect plant records first."
    )
    return {
        "proposal_id": "RP-reference_candidate_v2",
        "proposal_type": "reference_candidate_v2",
        "status": "pending_review",
        "created_at": _now(),
        "based_on_reference_id": "reference_v1",
        "candidate_reference_id": "reference_v2_candidate",
        "proposed_train_start": "",  # null — never fabricated without evidence
        "proposed_train_end": "",
        "context_scope": "to_be_determined",
        "sensor_scope": "all_supported_minus_excluded",
        "excluded_sensors": excluded,
        "model_refit_required": True,
        "approval_required": True,
        "source_incident_ids": incident_ids,
        "source_drift_event_ids": drift_ids,
        "evidence_summary": (
            f"Residual healthy-only drift: {residual['n_residual_windows']} of "
            f"{residual['n_windows']} sensor windows "
            f"({residual['residual_fraction'] * 100:.1f}%) after excluding "
            f"faulty/quarantined-sensor evidence; raw drift mass "
            f"{residual['raw_mass']:.1f} -> {residual['healthy_mass']:.1f} "
            f"({residual['reduction_pct']:.0f}% reduction). material={material}. "
            "This is a candidate design only. No model artifacts have been trained."
        ),
        "risk_summary": (
            "Refitting on a post-fault window risks baking instrumentation noise "
            "into the new reference; refit only after the channel is confirmed "
            "and the quarantine is approved."
        ),
        "required_human_records": "",
        "recommended_next_step": next_step,
    }


def _external_records_proposal(incident_ids: str, drift_ids: str) -> dict[str, Any]:
    return {
        "proposal_id": "RP-external_records_review",
        "proposal_type": "external_records_review",
        "status": "pending_review",
        "created_at": _now(),
        "based_on_reference_id": "reference_v1",
        "candidate_reference_id": "",
        "proposed_train_start": "",
        "proposed_train_end": "",
        "context_scope": "none",
        "sensor_scope": "all_supported_sensors",
        "excluded_sensors": "",
        "model_refit_required": False,
        "approval_required": True,
        "source_incident_ids": incident_ids,
        "source_drift_event_ids": drift_ids,
        "evidence_summary": (
            "External plant records are required to confirm the instrumentation "
            "channel failure and to interpret the residual healthy-only drift."
        ),
        "risk_summary": (
            "Without these records the instrumentation-vs-process question "
            "cannot be closed; proceeding to a refit would be premature."
        ),
        "required_human_records": (
            "maintenance log|sensor channel log|operator notes|setpoint changes"
        ),
        "recommended_next_step": (
            "Collect the listed plant records and attach them to this review."
        ),
    }


def build_reference_proposals(
    quarantine_sensors: list[str],
    residual: dict[str, Any],
    incidents: pd.DataFrame,
    drift_events: pd.DataFrame,
) -> pd.DataFrame:
    """The three mandatory candidate proposals (all ``pending_review``)."""
    excluded = _pipe(quarantine_sensors)
    incident_ids: list[str] = []
    drift_ids: list[str] = []
    for sensor in quarantine_sensors:
        incident_ids += _sensor_incident_ids(sensor, incidents)
        drift_ids += _sensor_drift_ids(sensor, drift_events)
    inc_str = _pipe(incident_ids)
    dr_str = _pipe(drift_ids)
    rows = [
        _quarantine_only_proposal(excluded, inc_str, dr_str),
        _candidate_v2_proposal(excluded, residual, inc_str, dr_str),
        _external_records_proposal(inc_str, dr_str),
    ]
    return pd.DataFrame(rows, columns=PROPOSAL_COLUMNS)
