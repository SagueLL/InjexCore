"""Drift scoring — normalized metrics, weighted evidence, severity.

Deliberately simple and documented (no ensemble logic): each metric is
normalized by a configured cap, combined as a weighted mean over the metrics
available for that window, adjusted for persistence, and cut into the drift
severity vocabulary. The sensor-health override then reclassifies sensor
windows that overlap strong instrumentation events as ``sensor_drift`` —
instrumentation failure is never presented as process degradation.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from src.intelligence.drift.policy import (
    GLOBAL_SCOPE_KEY,
    DriftPolicy,
    severity_from_score,
)

SCORED_COLUMNS = [
    "window_start",
    "window_end",
    "scope",
    "view",
    "entity",
    "profile",
    "drift_type",
    "drift_score",
    "uncalibrated_score",
    "is_train_window",
    "severity",
    "metric_scores",
    "n_rows",
    "n_valid",
    "sensor_health_override",
]

_GROUP_KEY = ["scope", "view", "entity", "profile"]


def default_drift_type(scope: str, entity: str) -> str:
    """Taxonomy default before the sensor-health override is applied."""
    if scope == "sensor":
        return "process_drift"
    if scope == "multivariate":
        return "multivariate_shift"
    if scope == "correlation":
        return "correlation_shift"
    if scope in ("context", "profile"):
        return "profile_composition_shift" if entity == "profile" else "context_shift"
    return "unknown_shift"


def _metric_scores_json(metrics: dict[str, tuple[float, float]]) -> str:
    """Compact ``{metric: {value, norm}}`` payload for one scored window."""
    payload = {
        m: {"value": round(v, 6), "norm": round(n, 4)}
        for m, (v, n) in sorted(metrics.items())
        if not np.isnan(n)
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def normalize_and_score(
    metric_rows: pd.DataFrame,
    policy: DriftPolicy,
    window_len: pd.Timedelta,
    train_end: pd.Timestamp,
) -> pd.DataFrame:
    """Long metric rows -> one scored row per (window, scope, view, entity, profile)."""
    if not len(metric_rows):
        return pd.DataFrame(columns=SCORED_COLUMNS)
    caps = policy.scoring.metric_caps
    weights = policy.scoring.metric_weights

    rows: list[dict[str, Any]] = []
    grouped = metric_rows.groupby(
        ["window_start", *_GROUP_KEY], sort=True, dropna=False
    )
    for (window, scope, view, entity, profile), group in grouped:
        metrics: dict[str, tuple[float, float]] = {}
        score_num = score_den = 0.0
        for metric, value in zip(group["metric"], group["value"], strict=True):
            value = float(value)
            cap = caps.get(str(metric))
            if cap is None or cap <= 0 or np.isnan(value):
                metrics[str(metric)] = (value, float("nan"))
                continue
            norm = min(abs(value) / cap, 1.0)
            metrics[str(metric)] = (value, norm)
            weight = weights.get(str(metric), 1.0)
            score_num += weight * norm
            score_den += weight
        if score_den == 0.0:
            continue
        score = score_num / score_den
        window_start = pd.Timestamp(window)
        window_end = window_start + window_len
        rows.append(
            {
                "window_start": window_start,
                "window_end": window_end,
                "scope": scope,
                "view": view,
                "entity": entity,
                "profile": profile,
                "drift_type": default_drift_type(str(scope), str(entity)),
                "drift_score": score,
                "uncalibrated_score": score,
                "is_train_window": window_end <= train_end,
                "severity": "info",  # assigned after calibration + persistence
                "metric_scores": _metric_scores_json(metrics),
                "n_rows": int(group["n_rows"].max()),
                "n_valid": int(group["n_valid"].max()),
                "sensor_health_override": False,
            }
        )
    scored = pd.DataFrame(rows, columns=SCORED_COLUMNS)
    if not len(scored):
        return scored
    scored = scored.sort_values(
        [*_GROUP_KEY, "window_start"], kind="stable"
    ).reset_index(drop=True)
    scored = _calibrate_against_train(scored, policy)
    scored = _apply_persistence(scored, policy)
    scored["severity"] = [
        severity_from_score(s, policy.scoring.severity_thresholds)
        for s in scored["drift_score"]
    ]
    return scored


def _calibrate_against_train(scored: pd.DataFrame, policy: DriftPolicy) -> pd.DataFrame:
    """Rescale each group's scores against its own train-window envelope.

    ``calibrated = clip((score - train_quantile) / excess_cap, 0, 1)`` — a
    window drifts only by the margin it *exceeds* what the train period
    produced for the same (scope, view, entity, profile). Groups without
    enough train windows keep the uncalibrated score (and stay transparent
    via the ``uncalibrated_score`` column).
    """
    cfg = policy.scoring
    if not cfg.train_calibration:
        return scored
    scored = scored.copy()
    calibrated = scored["drift_score"].to_numpy().copy()
    for _, group in scored.groupby(_GROUP_KEY, sort=False):
        train_scores = group.loc[group["is_train_window"], "drift_score"]
        if len(train_scores) < cfg.train_calibration_min_windows:
            continue
        baseline = float(train_scores.quantile(cfg.train_calibration_quantile))
        excess = (group["drift_score"].to_numpy() - baseline) / cfg.excess_cap
        calibrated[group.index.to_numpy()] = np.clip(excess, 0.0, 1.0)
    scored["drift_score"] = calibrated
    return scored


def _apply_persistence(scored: pd.DataFrame, policy: DriftPolicy) -> pd.DataFrame:
    """Bonus for entities active over consecutive windows (capped at 1.0)."""
    threshold = policy.events.active_score_threshold
    min_windows = policy.scoring.persistence_min_windows
    bonus = policy.scoring.persistence_bonus
    adjusted = scored["drift_score"].to_numpy().copy()
    for _, group in scored.groupby(_GROUP_KEY, sort=False):
        run = 0
        for pos, score in zip(group.index, group["drift_score"], strict=True):
            run = run + 1 if score >= threshold else 0
            if run >= min_windows:
                adjusted[pos] = min(float(score) + bonus, 1.0)
    scored = scored.copy()
    scored["drift_score"] = adjusted
    return scored


def apply_sensor_health_override(
    scored: pd.DataFrame,
    sensor_health_events: pd.DataFrame,
    policy: DriftPolicy,
) -> pd.DataFrame:
    """Reclassify sensor windows overlapping strong instrumentation events.

    A sensor-scope window whose interval overlaps a strong-family
    sensor-health event for the same sensor by at least
    ``min_overlap_fraction`` of the window becomes ``sensor_drift``. Severity
    is never reduced by the override.
    """
    if (
        not policy.sensor_health_override.enabled
        or not len(scored)
        or not len(sensor_health_events)
    ):
        return scored
    families = set(policy.sensor_health_override.strong_issue_families)
    min_fraction = policy.sensor_health_override.min_overlap_fraction

    scored = scored.copy()
    sensor_rows = scored["scope"] == "sensor"
    for event in sensor_health_events.itertuples(index=False):
        event_families = {
            t.split(":")[0] for t in str(event.issue_types).split("|") if t
        }
        if not event_families & families:
            continue
        ev_start = pd.Timestamp(event.start_timestamp)
        ev_end = pd.Timestamp(event.end_timestamp)
        candidates = sensor_rows & (scored["entity"] == str(event.sensor))
        if not candidates.any():
            continue
        starts = scored.loc[candidates, "window_start"]
        ends = scored.loc[candidates, "window_end"]
        overlap = (
            (ends.clip(upper=ev_end) - starts.clip(lower=ev_start))
            .dt.total_seconds()
            .clip(lower=0.0)
        )
        window_seconds = (ends - starts).dt.total_seconds()
        hit = overlap / window_seconds >= min_fraction
        idx = starts.index[hit]
        scored.loc[idx, "drift_type"] = "sensor_drift"
        scored.loc[idx, "sensor_health_override"] = True
    return scored


def comparison_table(
    scored: pd.DataFrame,
    dominance_by_window: pd.Series,
    policy: DriftPolicy,
) -> pd.DataFrame:
    """Raw-vs-healthy-only window comparison (the headline addendum table).

    One row per (window, scope, entity, profile) present in either view:
    both scores, the delta, whether drift *remains* in the healthy view, the
    multivariate evidence dominance and the Level-A exclusion reason for
    windows dominated by faulty/quarantined sensors.
    """
    key = ["window_start", "scope", "entity", "profile"]
    raw = scored[scored["view"] == "raw"][[*key, "drift_score"]].rename(
        columns={"drift_score": "drift_score_raw"}
    )
    healthy = scored[scored["view"] == "healthy_only"][[*key, "drift_score"]].rename(
        columns={"drift_score": "drift_score_healthy_only"}
    )
    merged = raw.merge(healthy, on=key, how="outer")
    merged["delta"] = merged["drift_score_raw"] - merged["drift_score_healthy_only"]
    threshold = policy.events.active_score_threshold
    merged["residual_drift"] = (
        merged["drift_score_healthy_only"].fillna(0.0) >= threshold
    )
    merged["dominance"] = [
        float(dominance_by_window.get(w, float("nan")))
        if scope == "multivariate"
        else float("nan")
        for w, scope in zip(merged["window_start"], merged["scope"], strict=True)
    ]
    dominated = (
        merged["dominance"].fillna(0.0)
        >= policy.healthy_view.evidence_dominance_fraction
    )
    merged["exclusion_reason"] = np.where(
        dominated, "evidence_dominated_by_faulty_sensors", ""
    )
    return merged.sort_values(key, kind="stable").reset_index(drop=True)


def scope_summary(
    scored: pd.DataFrame, scope: str, active_threshold: float = 0.5
) -> pd.DataFrame:
    """Per-(entity, profile, view) aggregate for one scope's summary table."""
    subset = scored[scored["scope"] == scope]
    if not len(subset):
        return pd.DataFrame(
            columns=[
                "entity",
                "profile",
                "view",
                "n_windows",
                "mean_drift_score",
                "max_drift_score",
                "n_active_windows",
                "max_severity",
            ]
        )
    severity_rank = {"info": 0, "warning": 1, "anomaly": 2, "critical": 3}
    rows: list[dict[str, Any]] = []
    for (entity, profile, view), group in subset.groupby(["entity", "profile", "view"]):
        rows.append(
            {
                "entity": entity,
                "profile": profile,
                "view": view,
                "n_windows": int(len(group)),
                "mean_drift_score": float(group["drift_score"].mean()),
                "max_drift_score": float(group["drift_score"].max()),
                "n_active_windows": int(
                    (group["drift_score"] >= active_threshold).sum()
                ),
                "max_severity": max(
                    group["severity"], key=lambda s: severity_rank.get(str(s), 0)
                ),
            }
        )
    return (
        pd.DataFrame(rows)
        .sort_values("max_drift_score", ascending=False, kind="stable")
        .reset_index(drop=True)
    )


def profile_key_or_global(profile: str | None) -> str:
    """Normalize a profile key for grouping (None -> global)."""
    return GLOBAL_SCOPE_KEY if profile is None else str(profile)
