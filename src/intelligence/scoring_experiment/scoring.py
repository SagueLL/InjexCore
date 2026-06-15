"""Per-row scenario scoring — baseline + quarantine-aware interpretation.

The ``base`` frame joins the persisted anomaly scores with the operational
context timeline (both master-aligned). The quarantine-aware scenario flags
rows whose anomaly evidence is dominated by a pending-quarantine sensor and
down-ranks ONLY their review severity — original ``severity`` and
``combined_score`` are preserved verbatim; ``adjusted_review_score`` equals
``original_combined_score`` by construction because nothing is rescored.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from src.intelligence.scoring_experiment.quarantine import QuarantineWindow

BASELINE_SCENARIO = "baseline_v1"
QUARANTINE_SCENARIO = "quarantine_inlet_hopper_points_interpretive"

SCENARIO_SCORE_COLUMNS = [
    "timestamp",
    "profile",
    "scenario_id",
    "original_severity",
    "adjusted_review_severity",
    "original_combined_score",
    "adjusted_review_score",
    "suppressed_for_review",
    "suppression_reason",
    "dominant_faulty_sensor",
    "sensor_health_context",
    "steam_context",
    "bom_context_status",
    "product_code",
    "recipe_context_key",
    "evidence",
]

_CONTEXT_COLUMNS = [
    "sensor_health_context",
    "steam_context",
    "bom_context_status",
    "product_code",
    "recipe_context_key",
    "faulty_sensors",
    "quarantine_recommended_sensors",
]


def build_base(anomaly: pd.DataFrame, op_timeline: pd.DataFrame) -> pd.DataFrame:
    """Join anomaly scores + operational context on the shared master index."""
    op = op_timeline.reindex(anomaly.index)
    base = pd.DataFrame(index=anomaly.index)
    base["profile"] = anomaly["profile"].astype(str)
    base["original_severity"] = anomaly["severity"].astype(str)
    base["original_combined_score"] = anomaly["combined_score"].astype(float)
    base["affected_variables"] = anomaly["affected_variables"].fillna("").astype(str)
    for col in _CONTEXT_COLUMNS:
        base[col] = (
            op[col].astype("string").fillna("").astype(str) if col in op.columns else ""
        )
    return base


def _contains_token(series: pd.Series, token: str) -> pd.Series:
    if not token:
        return pd.Series(False, index=series.index)
    pattern = rf"(?:^|\|){re.escape(token)}(?:\||$)"
    return series.astype(str).str.contains(pattern, regex=True)


def apply_quarantine(
    base: pd.DataFrame,
    targets: list[QuarantineWindow],
    burst_windows: list[QuarantineWindow],
) -> pd.DataFrame:
    """Add the quarantine-aware review columns (original columns untouched)."""
    index = base.index
    nonnormal = base["original_severity"].to_numpy() != "normal"
    dominant = pd.Series("", index=index, dtype="object")
    suppressed = pd.Series(False, index=index)
    reason = pd.Series("", index=index, dtype="object")

    for target in targets:
        in_window = (index >= target.start) & (index <= target.end)
        in_evidence = _contains_token(base["affected_variables"], target.sensor)
        faulty_now = _contains_token(
            base["faulty_sensors"], target.sensor
        ) | _contains_token(base["quarantine_recommended_sensors"], target.sensor)
        hit = nonnormal & in_window & in_evidence.to_numpy() & faulty_now.to_numpy()
        _assign(
            dominant,
            suppressed,
            reason,
            hit,
            target.sensor,
            "evidence_dominated_by_quarantined_sensor",
        )

    for window in burst_windows:
        in_window = (index >= window.start) & (index <= window.end)
        hit = nonnormal & in_window
        _assign(
            dominant,
            suppressed,
            reason,
            hit,
            window.sensor,
            "burst_explained_by_sensor_fault",
        )

    out = base.copy()
    out["dominant_faulty_sensor"] = dominant
    out["suppressed_for_review"] = suppressed
    out["suppression_reason"] = reason
    out["adjusted_review_severity"] = base["original_severity"].where(
        ~suppressed, "normal"
    )
    # Never rescored: the adjusted score is the original combined score.
    out["adjusted_review_score"] = base["original_combined_score"]
    return out


def _assign(
    dominant: pd.Series,
    suppressed: pd.Series,
    reason: pd.Series,
    hit: np.ndarray,
    sensor: str,
    why: str,
) -> None:
    """Record first-match dominance + suppression for the hit rows in place."""
    fresh = hit & (dominant.to_numpy() == "")
    dominant.loc[fresh] = sensor
    reason.loc[fresh] = why
    suppressed.loc[hit] = True


def _scenario_rows(base_oi: pd.DataFrame, scenario_id: str) -> pd.DataFrame:
    """Project the review subset into the §11.1 scenario_scores schema."""
    quarantine = scenario_id == QUARANTINE_SCENARIO
    frame = pd.DataFrame({"timestamp": base_oi.index})
    frame["profile"] = base_oi["profile"].to_numpy()
    frame["scenario_id"] = scenario_id
    frame["original_severity"] = base_oi["original_severity"].to_numpy()
    frame["adjusted_review_severity"] = (
        base_oi["adjusted_review_severity"].to_numpy()
        if quarantine
        else base_oi["original_severity"].to_numpy()
    )
    frame["original_combined_score"] = base_oi["original_combined_score"].to_numpy()
    frame["adjusted_review_score"] = base_oi["original_combined_score"].to_numpy()
    frame["suppressed_for_review"] = (
        base_oi["suppressed_for_review"].to_numpy() if quarantine else False
    )
    frame["suppression_reason"] = (
        base_oi["suppression_reason"].to_numpy() if quarantine else ""
    )
    frame["dominant_faulty_sensor"] = (
        base_oi["dominant_faulty_sensor"].to_numpy() if quarantine else ""
    )
    for col in (
        "sensor_health_context",
        "steam_context",
        "bom_context_status",
        "product_code",
        "recipe_context_key",
    ):
        frame[col] = base_oi[col].to_numpy()
    frame["evidence"] = base_oi["affected_variables"].to_numpy()
    return frame[SCENARIO_SCORE_COLUMNS]


def scenario_scores(base: pd.DataFrame) -> pd.DataFrame:
    """Long-format review table for both per-row scenarios.

    Restricted to rows that are non-normal in the baseline — the only rows
    where a review adjustment is meaningful. Full-population counts live in
    the comparison tables.
    """
    base_oi = base[base["original_severity"] != "normal"]
    frames = [
        _scenario_rows(base_oi, BASELINE_SCENARIO),
        _scenario_rows(base_oi, QUARANTINE_SCENARIO),
    ]
    return pd.concat(frames, ignore_index=True)
