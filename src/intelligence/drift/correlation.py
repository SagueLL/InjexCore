"""Correlation drift — classification of the persisted correlation shift.

Consumes the Correlation Intelligence run's train references and its
train-vs-validation shift table (one Pearson delta per (profile, pair)).
Windowed correlation recomputation is explicitly out of scope — drift here
re-reads what correlation already persisted and *classifies* it with
sensor-quality awareness: a pair shift dominated by a sensor with a strong
persistent instrumentation event is ``sensor_drift_evidence``, not a
``process_correlation_break``.

Upstream limitation (documented, not fabricated): the correlation run does
not persist validation Spearman values, so Spearman *changes* cannot be
ranked — train Spearman is carried as reference context only.
"""

from __future__ import annotations

import json

import pandas as pd

from src.intelligence.drift.policy import DriftPolicy

CLASSIFIED_COLUMNS = [
    "profile",
    "feature_a",
    "feature_b",
    "pearson_train",
    "pearson_validation",
    "abs_delta",
    "spearman_train",
    "change_class",
    "classification",
    "dominant_sensor",
    "evidence",
]

CHANGE_CLASSES = ("sign_flip", "newly_strong", "collapsed", "large_shift", "stable")


def strong_instrumentation_sensors(
    sensor_health_events: pd.DataFrame,
    validation_start: pd.Timestamp,
    validation_end: pd.Timestamp,
    policy: DriftPolicy,
) -> dict[str, str]:
    """Sensors whose strong persistent instrumentation events dominate validation.

    A sensor qualifies when one of its persistent events with an issue family
    in ``strong_issue_families`` covers at least ``min_overlap_fraction`` of
    the validation window. Returns ``{sensor: issue_families}``.
    """
    out: dict[str, str] = {}
    if not len(sensor_health_events):
        return out
    span = (validation_end - validation_start).total_seconds()
    if span <= 0:
        return out
    families = set(policy.sensor_health_override.strong_issue_families)
    for row in sensor_health_events.itertuples(index=False):
        if not bool(row.is_persistent):
            continue
        issue_families = {t.split(":")[0] for t in str(row.issue_types).split("|") if t}
        if not issue_families & families:
            continue
        start = max(pd.Timestamp(row.start_timestamp), validation_start)
        end = min(pd.Timestamp(row.end_timestamp), validation_end)
        overlap = max((end - start).total_seconds(), 0.0) / span
        if overlap >= policy.sensor_health_override.min_overlap_fraction:
            out[str(row.sensor)] = str(row.issue_types)
    return out


def _change_class(train: float, validation: float, policy: DriftPolicy) -> str:
    cfg = policy.correlation
    delta = abs(validation - train)
    if (
        train * validation < 0
        and abs(train) >= cfg.sign_flip_min_abs
        and abs(validation) >= cfg.sign_flip_min_abs
    ):
        return "sign_flip"
    if abs(train) < cfg.weak_threshold and abs(validation) >= cfg.strong_threshold:
        return "newly_strong"
    if abs(train) >= cfg.strong_threshold and abs(validation) < cfg.weak_threshold:
        return "collapsed"
    if delta >= cfg.material_delta:
        return "large_shift"
    return "stable"


def classify_pairs(
    correlations: pd.DataFrame,
    shift: pd.DataFrame,
    dominated_sensors: dict[str, str],
    policy: DriftPolicy,
) -> pd.DataFrame:
    """Classified correlation-shift table (one row per shifted pair)."""
    spearman = correlations.set_index(["profile", "feature_a", "feature_b"])["spearman"]
    rows: list[dict[str, object]] = []
    for row in shift.itertuples(index=False):
        train = float(row.pearson_train)
        validation = float(row.pearson_validation)
        change_class = _change_class(train, validation, policy)
        dominant = next(
            (
                s
                for s in (str(row.feature_a), str(row.feature_b))
                if s in dominated_sensors
            ),
            None,
        )
        material = change_class != "stable"
        if dominant is not None and material:
            classification = "sensor_drift_evidence"
        elif material:
            classification = "process_correlation_break"
        else:
            classification = "stable"
        evidence: dict[str, object] = {"abs_delta": round(abs(validation - train), 4)}
        if dominant is not None:
            evidence["instrumentation_events"] = dominated_sensors[dominant]
        rows.append(
            {
                "profile": str(row.profile),
                "feature_a": str(row.feature_a),
                "feature_b": str(row.feature_b),
                "pearson_train": train,
                "pearson_validation": validation,
                "abs_delta": float(row.abs_delta),
                "spearman_train": float(
                    spearman.get(
                        (str(row.profile), str(row.feature_a), str(row.feature_b)),
                        float("nan"),
                    )
                ),
                "change_class": change_class,
                "classification": classification,
                "dominant_sensor": dominant or "",
                "evidence": json.dumps(evidence, sort_keys=True, separators=(",", ":")),
            }
        )
    classified = pd.DataFrame(rows, columns=CLASSIFIED_COLUMNS)
    if len(classified):
        classified = classified.sort_values(
            "abs_delta", ascending=False, kind="stable"
        ).reset_index(drop=True)
    return classified


def summary_table(classified: pd.DataFrame, policy: DriftPolicy) -> pd.DataFrame:
    """Top-k shifted pairs per profile for the correlation drift summary."""
    if not len(classified):
        return classified
    return (
        classified[classified["change_class"] != "stable"]
        .groupby("profile", group_keys=False)[classified.columns]
        .head(policy.correlation.top_k_pairs)
        .reset_index(drop=True)
    )
