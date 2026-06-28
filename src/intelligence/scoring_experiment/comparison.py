"""Scenario comparison tables.

Computes the full-population counts that ``scenario_scores`` (restricted to
the review subset) does not carry: how the warning/anomaly picture changes
under the quarantine-aware interpretation, how the incident picture changes,
and what residual drift survives the healthy-only view. All counts come from
persisted artifacts; nothing is rescored.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from src.intelligence.scoring_experiment.scoring import BASELINE_SCENARIO

ANOMALY_RATE_COLUMNS = [
    "scenario_id",
    "rows_total",
    "original_warning_count",
    "original_anomaly_count",
    "adjusted_warning_count",
    "adjusted_anomaly_count",
    "suppressed_count",
    "suppression_rate",
    "remaining_warning_count",
    "remaining_anomaly_count",
    "healthy_only_residual_count",
    "top_remaining_sensors",
    "top_remaining_profiles",
    "top_remaining_contexts",
    "interpretation",
]

INCIDENT_COMPARISON_COLUMNS = [
    "scenario_id",
    "n_incidents",
    "n_anomaly_burst_incidents",
    "n_suppressed_incidents",
    "n_quarantine_dominated_incidents",
    "interpretation",
]

DRIFT_COMPARISON_COLUMNS = [
    "scenario_id",
    "view",
    "scope_or_profile",
    "n_windows",
    "raw_mass",
    "healthy_mass",
    "reduction_pct",
    "n_residual_windows",
    "interpretation",
]


def _top_tokens(series: pd.Series, top: int) -> str:
    """Most common pipe-joined tokens across a string column."""
    counts: dict[str, int] = {}
    for value in series.fillna("").astype(str):
        for token in value.split("|"):
            if token:
                counts[token] = counts.get(token, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return "|".join(f"{name}:{n}" for name, n in ordered[:top])


def anomaly_rate_comparison(
    base: pd.DataFrame, residual_count: int, top: int, quarantine_scenario: str
) -> pd.DataFrame:
    """Per-scenario warning/anomaly counts before and after suppression.

    The quarantine scenario row is omitted when there is no pending quarantine
    proposal (``quarantine_scenario == ""``).
    """
    rows_total = int(len(base))
    sev = base["original_severity"]
    orig_warn = int((sev == "warning").sum())
    orig_anom = int((sev == "anomaly").sum())
    nonnormal = sev != "normal"

    suppressed = base["row_suppressed_for_review"]
    adj = base["adjusted_review_severity"]
    adj_warn = int((adj == "warning").sum())
    adj_anom = int((adj == "anomaly").sum())
    n_suppressed = int(suppressed.sum())
    suppression_rate = n_suppressed / int(nonnormal.sum()) if nonnormal.sum() else 0.0

    remaining = base[adj != "normal"]
    rows = [
        {
            "scenario_id": BASELINE_SCENARIO,
            "rows_total": rows_total,
            "original_warning_count": orig_warn,
            "original_anomaly_count": orig_anom,
            "adjusted_warning_count": orig_warn,
            "adjusted_anomaly_count": orig_anom,
            "suppressed_count": 0,
            "suppression_rate": 0.0,
            "remaining_warning_count": orig_warn,
            "remaining_anomaly_count": orig_anom,
            "healthy_only_residual_count": 0,
            "top_remaining_sensors": _top_tokens(
                base.loc[nonnormal, "affected_variables"], top
            ),
            "top_remaining_profiles": _top_tokens(base.loc[nonnormal, "profile"], top),
            "top_remaining_contexts": _top_tokens(
                base.loc[nonnormal, "sensor_health_context"], top
            ),
            "interpretation": (
                "Original persisted picture: the anomaly mass includes "
                "instrumentation-dominated rows."
            ),
        },
    ]
    if quarantine_scenario:
        rows.append(
            {
                "scenario_id": quarantine_scenario,
                "rows_total": rows_total,
                "original_warning_count": orig_warn,
                "original_anomaly_count": orig_anom,
                "adjusted_warning_count": adj_warn,
                "adjusted_anomaly_count": adj_anom,
                "suppressed_count": n_suppressed,
                "suppression_rate": suppression_rate,
                "remaining_warning_count": adj_warn,
                "remaining_anomaly_count": adj_anom,
                "healthy_only_residual_count": int(residual_count),
                "top_remaining_sensors": _top_tokens(
                    remaining["affected_variables"], top
                ),
                "top_remaining_profiles": _top_tokens(remaining["profile"], top),
                "top_remaining_contexts": _top_tokens(
                    remaining["sensor_health_context"], top
                ),
                "interpretation": (
                    f"After down-ranking quarantine-dominated rows for review, "
                    f"{n_suppressed} of {int(nonnormal.sum())} non-normal rows are "
                    f"suppressed ({suppression_rate * 100:.0f}%); the remaining "
                    "rows are the genuine review backlog. Interpretive only — no "
                    "score was changed."
                ),
            }
        )
    return pd.DataFrame(rows, columns=ANOMALY_RATE_COLUMNS)


def _contains_token(series: pd.Series, token: str) -> pd.Series:
    pattern = rf"(?:^|\|){re.escape(token)}(?:\||$)"
    return series.fillna("").astype(str).str.contains(pattern, regex=True)


def incident_comparison(
    incidents: pd.DataFrame,
    suppressed: pd.DataFrame,
    quarantine_sensors: list[str],
    quarantine_scenario: str,
) -> pd.DataFrame:
    """How the incident picture reads under the quarantine interpretation."""
    n_incidents = int(len(incidents))
    n_burst = (
        int((incidents["incident_type"] == "anomaly_burst").sum()) if n_incidents else 0
    )
    dominated = 0
    if n_incidents and quarantine_sensors:
        mask = incidents["incident_type"].isin(["sensor_fault", "sensor_warning"])
        sensor_mask = pd.Series(False, index=incidents.index)
        for sensor in quarantine_sensors:
            sensor_mask = sensor_mask | _contains_token(
                incidents["affected_sensors"], sensor
            )
        dominated = int((mask & sensor_mask).sum())
    rows = [
        {
            "scenario_id": BASELINE_SCENARIO,
            "n_incidents": n_incidents,
            "n_anomaly_burst_incidents": n_burst,
            "n_suppressed_incidents": 0,
            "n_quarantine_dominated_incidents": 0,
            "interpretation": "Original incident picture, as aggregated.",
        },
    ]
    if quarantine_scenario:
        rows.append(
            {
                "scenario_id": quarantine_scenario,
                "n_incidents": n_incidents,
                "n_anomaly_burst_incidents": n_burst,
                "n_suppressed_incidents": int(len(suppressed)),
                "n_quarantine_dominated_incidents": dominated,
                "interpretation": (
                    f"{len(suppressed)} burst incident(s) already explained by a "
                    f"sensor fault; {dominated} sensor incident(s) on the "
                    "quarantine target(s). Associative only; nothing approved."
                ),
            }
        )
    return pd.DataFrame(rows, columns=INCIDENT_COMPARISON_COLUMNS)


def drift_comparison(raw_vs_healthy: pd.DataFrame, top: int) -> pd.DataFrame:
    """Healthy-only proxy view + per-profile residual (drift run, read-only)."""
    sensor = (
        raw_vs_healthy[raw_vs_healthy["scope"] == "sensor"].copy()
        if len(raw_vs_healthy)
        else raw_vs_healthy
    )
    rows: list[dict[str, Any]] = [_drift_row("healthy_only_proxy", "overall", sensor)]
    if len(sensor):
        per_profile = (
            sensor.groupby("profile")["residual_drift"]
            .sum()
            .sort_values(ascending=False)
        )
        for profile, _ in list(per_profile.items())[:top]:
            rows.append(
                _drift_row(
                    "candidate_reference_needed",
                    str(profile),
                    sensor[sensor["profile"] == profile],
                )
            )
    return pd.DataFrame(rows, columns=DRIFT_COMPARISON_COLUMNS)


def _drift_row(
    scenario_id: str, scope_or_profile: str, frame: pd.DataFrame
) -> dict[str, Any]:
    n = int(len(frame))
    raw_mass = float(frame["drift_score_raw"].fillna(0.0).sum()) if n else 0.0
    healthy_mass = (
        float(frame["drift_score_healthy_only"].fillna(0.0).sum()) if n else 0.0
    )
    n_residual = int(frame["residual_drift"].sum()) if n else 0
    reduction = (raw_mass - healthy_mass) / raw_mass * 100.0 if raw_mass > 0 else 0.0
    return {
        "scenario_id": scenario_id,
        "view": "proxy",
        "scope_or_profile": scope_or_profile,
        "n_windows": n,
        "raw_mass": raw_mass,
        "healthy_mass": healthy_mass,
        "reduction_pct": reduction,
        "n_residual_windows": n_residual,
        "interpretation": (
            "Labeled healthy-only proxy from the drift run; no PCA/Mahalanobis "
            "recomputation."
        ),
    }
