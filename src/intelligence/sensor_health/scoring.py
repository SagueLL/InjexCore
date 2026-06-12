"""Scoring — rule activations become per-(timestamp, sensor) health verdicts.

The score is deliberately simple and fully explainable:
``health_score = min(1, max(base x strength) + bonus x (n_families - 1))``.
Status is rule-derived (not back-derived from the score):

* ``faulty``  — a strong rule active for a persistent contiguous run, OR two
  corroborating families with a high score, OR flatline_zero on a sensor
  whose train window shows zero is abnormal.
* ``warning`` — any rule active otherwise.
* ``unknown`` — value missing (or trailing availability collapsed) with no
  rule active: honest, not "healthy by absence of evidence".
* ``healthy`` — otherwise.

Rule-level evidence stays visible: ``active_issue_types`` + a compact JSON
evidence string per flagged row.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.intelligence.sensor_health.policy import SensorHealthPolicy
from src.intelligence.sensor_health.rules import (
    RuleReferences,
    RuleResult,
    run_segments,
)


@dataclass
class SensorScore:
    """Per-row verdict arrays for one sensor."""

    sensor: str
    status: np.ndarray  # object: healthy/warning/faulty/unknown
    score: np.ndarray  # float [0, 1]
    issue_types: np.ndarray  # object, pipe-joined ("" when none)
    evidence: np.ndarray  # object, compact JSON ("" when none)


def _row_base(result: RuleResult, policy: SensorHealthPolicy) -> np.ndarray:
    """Base score per row (counter_reset sub-state aware)."""
    bases = policy.scoring.rule_base_scores
    default = bases.get(result.issue_type, 0.5)
    if result.substates is None:
        return np.where(result.mask, default, 0.0)
    recovered = bases.get("counter_reset_recovered", default)
    out = np.where(result.mask, default, 0.0)
    out[result.substates == "recovered_after_reset"] = recovered
    return out


def _row_tokens(result: RuleResult) -> tuple[np.ndarray, str]:
    """Per-row issue token (counter sub-state inlined) + family name."""
    if result.substates is None:
        tokens = np.where(result.mask, result.issue_type, "")
        return tokens.astype(object), result.issue_type
    tokens = np.full(len(result.mask), "", dtype=object)
    active = result.mask
    tokens[active] = [
        f"{result.issue_type}:{s}" if s else result.issue_type
        for s in result.substates[active]
    ]
    return tokens, result.issue_type


def score_sensor(
    sensor: str,
    values: np.ndarray,
    results: list[RuleResult],
    refs: RuleReferences,
    policy: SensorHealthPolicy,
) -> SensorScore:
    """Combine one sensor's rule results into status/score/evidence arrays."""
    sc = policy.scoring
    n = len(values)
    weighted_max = np.zeros(n)
    n_active = np.zeros(n, dtype=int)
    strong_active = np.zeros(n, dtype=bool)
    fz_abnormal = np.zeros(n, dtype=bool)
    token_arrays: list[np.ndarray] = []
    strengths: list[tuple[np.ndarray, np.ndarray]] = []

    zfrac = refs.train_zero_fraction.get(sensor, float("nan"))
    abnormal_zero = (
        np.isfinite(zfrac)
        and zfrac < policy.rules.flatline_zero.abnormal_train_zero_fraction
    )
    for result in results:
        base = _row_base(result, policy)
        weighted_max = np.maximum(weighted_max, base * result.strength)
        n_active += result.mask.astype(int)
        strong_active |= result.mask & (base >= sc.strong_rule_min_base)
        if result.issue_type == "flatline_zero" and abnormal_zero:
            fz_abnormal |= result.mask
        tokens, _family = _row_tokens(result)
        token_arrays.append(tokens)
        strengths.append((result.mask, result.strength))

    any_active = n_active > 0
    score = np.where(
        any_active,
        np.minimum(1.0, weighted_max + sc.corroboration_bonus * (n_active - 1)),
        0.0,
    )
    status = _statuses(
        values, any_active, n_active, score, strong_active, fz_abnormal, sc
    )
    issue_types, evidence = _row_evidence(token_arrays, strengths, any_active)
    return SensorScore(sensor, status, np.round(score, 4), issue_types, evidence)


def _statuses(
    values: np.ndarray,
    any_active: np.ndarray,
    n_active: np.ndarray,
    score: np.ndarray,
    strong_active: np.ndarray,
    fz_abnormal: np.ndarray,
    sc: object,
) -> np.ndarray:
    """Apply the documented status policy (priority order)."""
    n = len(values)
    persistent_strong = np.zeros(n, dtype=bool)
    for i, j in run_segments(strong_active):
        if j - i >= sc.persistent_min_rows:  # type: ignore[attr-defined]
            persistent_strong[i:j] = True
    corroborated = (n_active >= 2) & (score >= 0.7)
    faulty = persistent_strong | corroborated | fz_abnormal

    valid = ~np.isnan(values)
    window = sc.unknown_availability_window_rows  # type: ignore[attr-defined]
    valid_frac = (
        pd.Series(valid.astype(float)).rolling(window, min_periods=1).mean().to_numpy()
    )
    low_avail = ~valid | (
        valid_frac < sc.unknown_min_valid_fraction  # type: ignore[attr-defined]
    )
    status = np.full(n, "healthy", dtype=object)
    status[low_avail & ~any_active] = "unknown"
    status[any_active] = "warning"
    status[faulty] = "faulty"
    return status


def _row_evidence(
    token_arrays: list[np.ndarray],
    strengths: list[tuple[np.ndarray, np.ndarray]],
    any_active: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Pipe-joined issue tokens + compact JSON evidence for flagged rows."""
    n = len(any_active)
    issue_types = np.full(n, "", dtype=object)
    evidence = np.full(n, "", dtype=object)
    for row in np.flatnonzero(any_active):
        entries: dict[str, float] = {}
        for tokens, (mask, strength) in zip(token_arrays, strengths, strict=True):
            if mask[row]:
                entries[str(tokens[row])] = round(float(strength[row]), 4)
        issue_types[row] = "|".join(sorted(entries))
        evidence[row] = json.dumps(entries, sort_keys=True, separators=(",", ":"))
    return issue_types, evidence


def score_sensors(
    df: pd.DataFrame,
    sensors: list[str],
    rule_results: dict[str, list[RuleResult]],
    refs: RuleReferences,
    policy: SensorHealthPolicy,
) -> dict[str, SensorScore]:
    return {
        sensor: score_sensor(
            sensor,
            df[sensor].to_numpy(dtype=float),
            rule_results[sensor],
            refs,
            policy,
        )
        for sensor in sensors
    }


def to_scores_frame(
    timestamps: pd.Index,
    profiles: np.ndarray,
    per_sensor: dict[str, SensorScore],
    quarantine_rows: dict[str, np.ndarray],
) -> pd.DataFrame:
    """Long-form ``sensor_health_scores`` frame (sensor-major, time-sorted)."""
    frames = []
    for sensor in sorted(per_sensor):
        s = per_sensor[sensor]
        frames.append(
            pd.DataFrame(
                {
                    "timestamp": timestamps.to_numpy(),
                    "sensor": sensor,
                    "profile": profiles,
                    "health_status": s.status,
                    "health_score": s.score,
                    "active_issue_types": s.issue_types,
                    "evidence": s.evidence,
                    "quarantine_recommended": quarantine_rows.get(
                        sensor, np.zeros(len(timestamps), dtype=bool)
                    ),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def quality_timeline(
    timestamps: pd.Index,
    per_sensor: dict[str, SensorScore],
    quarantine_rows: dict[str, np.ndarray],
) -> pd.DataFrame:
    """Per-timestamp context the Operational Context layer consumes."""
    sensors = sorted(per_sensor)
    n = len(timestamps)
    status = np.stack([per_sensor[s].status for s in sensors])
    faulty = status == "faulty"
    warning = status == "warning"
    unknown = status == "unknown"
    quarantine = np.stack(
        [quarantine_rows.get(s, np.zeros(n, dtype=bool)) for s in sensors]
    )

    evaluated = len(sensors) - unknown.sum(axis=0)
    context = np.full(n, "all_sensors_healthy", dtype=object)
    context[evaluated == 0] = "unknown"
    context[warning.any(axis=0)] = "sensor_warning"
    context[faulty.any(axis=0)] = "sensor_faulty"

    names = np.array(sensors, dtype=object)

    def join_rows(matrix: np.ndarray) -> np.ndarray:
        out = np.full(n, "", dtype=object)
        for row in np.flatnonzero(matrix.any(axis=0)):
            out[row] = "|".join(names[matrix[:, row]])
        return out

    return pd.DataFrame(
        {
            "timestamp": timestamps.to_numpy(),
            "sensor_health_context": context,
            "faulty_sensors": join_rows(faulty),
            "warning_sensors": join_rows(warning),
            "quarantine_recommended_sensors": join_rows(quarantine),
            "unknown_sensors": join_rows(unknown),
            "n_sensors_evaluated": evaluated,
        }
    )
