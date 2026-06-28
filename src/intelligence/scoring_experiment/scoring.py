"""Per-row scenario scoring — baseline + quarantine-aware interpretation.

The ``base`` frame joins the persisted anomaly scores with the operational
context timeline (both master-aligned). The quarantine-aware scenario flags
rows whose anomaly evidence is dominated by a pending-quarantine sensor and
down-ranks ONLY their review severity — original ``severity`` and
``combined_score`` are preserved verbatim; ``adjusted_review_score`` equals
``original_combined_score`` by construction because nothing is rescored.

Two notions are kept strictly separate (LOG-01):

* **incident-level explained-burst coverage** — a non-normal row lying inside
  an anomaly-burst window already explained by a sensor fault
  (``incident_explained_for_review``). This is a property of the window.
* **row-level review suppression** — a row is only down-ranked when it carries
  its *own* row-level evidence for the faulty sensor
  (``row_suppressed_for_review`` + ``row_level_evidence_match``). An unrelated
  process anomaly inside the same window is reported as incident-explained but
  is **not** suppressed.

The quarantine scenario id is derived from the pending proposal sensor(s), not
hardcoded (GOV-02): one target -> ``quarantine_<sensor>_interpretive``, several
-> ``quarantine_proposals_interpretive``, none -> no quarantine scenario.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from src.intelligence.scoring_experiment.quarantine import QuarantineWindow

BASELINE_SCENARIO = "baseline_v1"
QUARANTINE_SCENARIO_MULTI = "quarantine_proposals_interpretive"

SCENARIO_SCORE_COLUMNS = [
    "timestamp",
    "profile",
    "scenario_id",
    "original_severity",
    "adjusted_review_severity",
    "original_combined_score",
    "adjusted_review_score",
    "row_suppressed_for_review",
    "incident_explained_for_review",
    "incident_level_explanation_match",
    "row_level_evidence_match",
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


def sanitize_sensor(name: str) -> str:
    """Deterministic identifier-safe form of a sensor name."""
    return re.sub(r"[^0-9A-Za-z_]+", "_", str(name)).strip("_") or "sensor"


def quarantine_scenario_id(sensors: list[str]) -> str:
    """Scenario id for the pending quarantine target(s); ``""`` when none."""
    uniq = list(dict.fromkeys(s for s in sensors if s))
    if not uniq:
        return ""
    if len(uniq) == 1:
        return f"quarantine_{sanitize_sensor(uniq[0])}_interpretive"
    return QUARANTINE_SCENARIO_MULTI


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


def _row_evidence(base: pd.DataFrame, sensor: str) -> np.ndarray:
    """Row-level evidence: the row's own anomaly attribution names the sensor.

    Affected-variable dominance is the row-discriminating signal. The per-row
    faulty/quarantine-recommended context is window-wide during a fault, so
    using it alone would suppress every row in the window — exactly the
    over-suppression LOG-01 forbids; it only *strengthens* an affected-variable
    match here.
    """
    return _contains_token(base["affected_variables"], sensor).to_numpy()


def apply_quarantine(
    base: pd.DataFrame,
    targets: list[QuarantineWindow],
    burst_windows: list[QuarantineWindow],
) -> pd.DataFrame:
    """Add the quarantine-aware review columns (original columns untouched)."""
    index = base.index
    nonnormal = base["original_severity"].to_numpy() != "normal"
    dominant = pd.Series("", index=index, dtype="object")
    reason = pd.Series("", index=index, dtype="object")
    suppressed = pd.Series(False, index=index)
    row_evidence = pd.Series(False, index=index)
    incident_explained = pd.Series(False, index=index)

    # Pending quarantine proposals: down-rank a row only when its own anomaly
    # evidence is dominated by the proposed sensor AND the sensor is faulty then.
    for target in targets:
        in_window = (index >= target.start) & (index <= target.end)
        in_evidence = _row_evidence(base, target.sensor)
        faulty_now = (
            _contains_token(base["faulty_sensors"], target.sensor)
            | _contains_token(base["quarantine_recommended_sensors"], target.sensor)
        ).to_numpy()
        hit = nonnormal & in_window & in_evidence & faulty_now
        _assign(
            dominant,
            reason,
            suppressed,
            row_evidence,
            hit,
            target.sensor,
            "evidence_dominated_by_quarantined_sensor",
        )

    # Explained anomaly-burst windows: incident-level coverage is recorded for
    # every non-normal row, but suppression STILL requires the row's own
    # row-level evidence for the explaining sensor (LOG-01).
    for window in burst_windows:
        in_window = (index >= window.start) & (index <= window.end)
        covered = nonnormal & in_window
        incident_explained.loc[covered] = True
        hit = covered & _row_evidence(base, window.sensor)
        _assign(
            dominant,
            reason,
            suppressed,
            row_evidence,
            hit,
            window.sensor,
            "burst_explained_by_sensor_fault",
        )

    out = base.copy()
    out["dominant_faulty_sensor"] = dominant
    out["row_suppressed_for_review"] = suppressed
    out["row_level_evidence_match"] = row_evidence
    out["incident_explained_for_review"] = incident_explained
    out["incident_level_explanation_match"] = incident_explained
    out["suppression_reason"] = reason
    out["adjusted_review_severity"] = base["original_severity"].where(
        ~suppressed, "normal"
    )
    # Never rescored: the adjusted score is the original combined score.
    out["adjusted_review_score"] = base["original_combined_score"]
    return out


def _assign(
    dominant: pd.Series,
    reason: pd.Series,
    suppressed: pd.Series,
    row_evidence: pd.Series,
    hit: np.ndarray,
    sensor: str,
    why: str,
) -> None:
    """Record first-match dominance + suppression for the hit rows in place."""
    fresh = hit & (dominant.to_numpy() == "")
    dominant.loc[fresh] = sensor
    reason.loc[fresh] = why
    suppressed.loc[hit] = True
    row_evidence.loc[hit] = True


def _scenario_rows(
    base_oi: pd.DataFrame, scenario_id: str, *, quarantine: bool
) -> pd.DataFrame:
    """Project the review subset into the §11.1 scenario_scores schema."""
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

    n = len(base_oi)
    falses = np.zeros(n, dtype=bool)
    blanks = np.array([""] * n, dtype=object)
    frame["row_suppressed_for_review"] = (
        base_oi["row_suppressed_for_review"].to_numpy() if quarantine else falses
    )
    frame["incident_explained_for_review"] = (
        base_oi["incident_explained_for_review"].to_numpy() if quarantine else falses
    )
    frame["incident_level_explanation_match"] = (
        base_oi["incident_level_explanation_match"].to_numpy() if quarantine else falses
    )
    frame["row_level_evidence_match"] = (
        base_oi["row_level_evidence_match"].to_numpy() if quarantine else falses
    )
    frame["suppression_reason"] = (
        base_oi["suppression_reason"].to_numpy() if quarantine else blanks
    )
    frame["dominant_faulty_sensor"] = (
        base_oi["dominant_faulty_sensor"].to_numpy() if quarantine else blanks
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


def scenario_scores(base: pd.DataFrame, quarantine_scenario: str) -> pd.DataFrame:
    """Long-format review table for the baseline + quarantine scenarios.

    Restricted to rows that are non-normal in the baseline — the only rows
    where a review adjustment is meaningful. The quarantine scenario is omitted
    when there is no pending quarantine proposal (``quarantine_scenario == ""``).
    """
    base_oi = base[base["original_severity"] != "normal"]
    frames = [_scenario_rows(base_oi, BASELINE_SCENARIO, quarantine=False)]
    if quarantine_scenario:
        frames.append(_scenario_rows(base_oi, quarantine_scenario, quarantine=True))
    return pd.concat(frames, ignore_index=True)
