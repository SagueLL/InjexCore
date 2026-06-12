"""Score normalization, combination and severity — fitted on train only.

Raw detector scores live on incompatible scales (robust z, D², SPE, isolation
score). Each is normalized to [0, 1] through the empirical CDF of its own
*training* scores per (profile, detector) — a quantile grid persisted with
the run, so later scoring reproduces the exact same normalization. The
combined score is a deliberately simple, documented rule:

* ``max`` (default) — conservative: the worst detector wins;
* ``weighted_mean`` — configurable weights over the available detectors.

Severity (``normal`` / ``warning`` / ``anomaly``) comes from percentiles of
the training combined score per profile. Rows whose profile no detector
supports are labelled ``unscored`` — never silently "normal".
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.intelligence._common.reporting import Finding, Severity
from src.intelligence.anomaly.policy import AnomalyPolicy

CHECK = "anomaly_combine"

DETECTORS = ("statistical", "mahalanobis", "pca_q", "pca_t2", "isolation_forest")
SCORE_COLUMNS = {d: f"{d}_score" for d in DETECTORS}
SEVERITY_UNSCORED = "unscored"

_GRID_POINTS = 1001
_MIN_CALIBRATION_SCORES = 50


@dataclass(frozen=True)
class CombineModel:
    """Train-fitted normalization grids + severity thresholds."""

    grids: dict[str, dict[str, np.ndarray]]  # profile -> detector -> quantile grid
    severity_thresholds: dict[str, tuple[float, float]]  # profile -> (warn, anom)
    trigger_levels: dict[str, float]  # detector -> normalized trigger in [0, 1]


def _trigger_levels(policy: AnomalyPolicy) -> dict[str, float]:
    base = policy.combine.trigger_percentile / 100.0
    return {
        "statistical": base,
        "mahalanobis": base,
        "isolation_forest": base,
        "pca_q": policy.pca_detector.q_threshold_percentile / 100.0,
        "pca_t2": policy.pca_detector.t2_threshold_percentile / 100.0,
    }


def _normalize(raw: pd.DataFrame, grids: dict[str, np.ndarray]) -> pd.DataFrame:
    """ECDF-normalize raw scores against the train grids (NaN preserved)."""
    out = pd.DataFrame(np.nan, index=raw.index, columns=list(DETECTORS))
    for detector, grid in grids.items():
        values = raw[detector].to_numpy(dtype=float)
        norm = np.searchsorted(grid, values, side="right") / len(grid)
        norm = np.clip(norm, 0.0, 1.0)
        norm[~np.isfinite(values)] = np.nan
        out[detector] = norm
    return out


def _combined(norm: pd.DataFrame, policy: AnomalyPolicy) -> pd.Series:
    cp = policy.combine
    if cp.method == "max":
        return norm.max(axis=1, skipna=True)
    weights = pd.Series({d: cp.weights.get(d, 0.0) for d in DETECTORS})
    weighted = norm.mul(weights, axis=1)
    weight_sum = norm.notna().mul(weights, axis=1).sum(axis=1)
    return weighted.sum(axis=1, skipna=True) / weight_sum.replace(0.0, np.nan)


def fit(
    raw: pd.DataFrame,
    labels: pd.Series,
    train_mask: pd.Series,
    policy: AnomalyPolicy,
) -> tuple[CombineModel, list[Finding]]:
    """Fit normalization grids + severity thresholds on training rows only."""
    findings: list[Finding] = []
    grids: dict[str, dict[str, np.ndarray]] = {}
    severity_thresholds: dict[str, tuple[float, float]] = {}

    quantile_points = np.linspace(0.0, 1.0, _GRID_POINTS)
    for profile in sorted(labels.unique()):
        prof_train = train_mask & (labels == profile)
        if not prof_train.any():
            continue
        prof_grids: dict[str, np.ndarray] = {}
        for detector in DETECTORS:
            values = raw.loc[prof_train, detector].dropna()
            if len(values) < _MIN_CALIBRATION_SCORES:
                if len(values):
                    findings.append(
                        Finding(
                            check=CHECK,
                            severity=Severity.AWARE,
                            finding_type="detector_under_calibration_floor",
                            column=detector,
                            count=int(len(values)),
                            action_taken="skip_detector_for_profile",
                            evidence={
                                "profile": profile,
                                "min_scores": _MIN_CALIBRATION_SCORES,
                            },
                        )
                    )
                continue
            prof_grids[detector] = np.quantile(values.to_numpy(), quantile_points)
        if not prof_grids:
            continue
        grids[profile] = prof_grids

        norm = _normalize(raw.loc[prof_train], prof_grids)
        combined = _combined(norm, policy)
        severity_thresholds[profile] = (
            float(np.nanpercentile(combined, policy.combine.warning_percentile)),
            float(np.nanpercentile(combined, policy.combine.anomaly_percentile)),
        )
        findings.append(
            Finding(
                check=CHECK,
                severity=Severity.NORMAL,
                finding_type="profile_thresholds_fit",
                column=profile,
                action_taken="fit_on_train",
                evidence={
                    "detectors": sorted(prof_grids),
                    "warning_threshold": round(severity_thresholds[profile][0], 6),
                    "anomaly_threshold": round(severity_thresholds[profile][1], 6),
                },
            )
        )

    model = CombineModel(
        grids=grids,
        severity_thresholds=severity_thresholds,
        trigger_levels=_trigger_levels(policy),
    )
    return model, findings


def _evidence_payload(
    raw_row: np.ndarray,
    norm_row: np.ndarray,
    triggered: list[str],
    affected: str,
) -> str:
    scores = {
        d: {
            "raw": round(float(raw_row[j]), 6),
            "normalized": round(float(norm_row[j]), 6),
        }
        for j, d in enumerate(DETECTORS)
        if np.isfinite(raw_row[j])
    }
    signals = [s for s in affected.split("|") if s]
    note = "Unusual behaviour relative to the profile's training reference."
    if signals:
        note = (
            "Unusual behaviour detected. Primary contributing signals: "
            + ", ".join(signals)
            + "."
        )
    return json.dumps(
        {"detectors": scores, "triggered": triggered, "note": note},
        ensure_ascii=False,
    )


def apply(
    raw: pd.DataFrame,
    labels: pd.Series,
    model: CombineModel,
    policy: AnomalyPolicy,
    affected_sources: dict[str, pd.Series],
) -> pd.DataFrame:
    """Produce the final scored frame (spec schema) for all rows."""
    norm_all = pd.DataFrame(np.nan, index=raw.index, columns=list(DETECTORS))
    combined = pd.Series(np.nan, index=raw.index)
    severity = pd.Series(SEVERITY_UNSCORED, index=raw.index, dtype=str)

    for profile, prof_grids in model.grids.items():
        mask = (labels == profile).to_numpy()
        if not mask.any():
            continue
        norm = _normalize(raw.loc[mask], prof_grids)
        norm_all.loc[mask] = norm.to_numpy()
        prof_combined = _combined(norm, policy)
        combined.loc[mask] = prof_combined.to_numpy()

        warn, anom = model.severity_thresholds[profile]
        prof_severity = np.where(
            prof_combined.isna(),
            SEVERITY_UNSCORED,
            np.where(
                prof_combined >= anom,
                "anomaly",
                np.where(prof_combined >= warn, "warning", "normal"),
            ),
        )
        severity.loc[mask] = prof_severity

    # Triggered detectors: normalized score at/above the detector's level.
    # Positional numpy access throughout — index-based lookups are far too
    # slow at master-dataset scale.
    trig = {
        d: (norm_all[d] >= model.trigger_levels[d]).fillna(False).to_numpy()
        for d in DETECTORS
    }
    triggered = pd.Series(
        ["|".join(d for d in DETECTORS if trig[d][i]) for i in range(len(raw))],
        index=raw.index,
        dtype=str,
    )

    # Affected variables: union over *triggered* interpretable detectors,
    # first-seen order, deduplicated. Isolation Forest contributes none.
    flagged_pos = np.flatnonzero(severity.isin(["warning", "anomaly"]).to_numpy())
    sources = {d: s.to_numpy() for d, s in affected_sources.items()}
    raw_np = raw[list(DETECTORS)].to_numpy(dtype=float)
    norm_np = norm_all[list(DETECTORS)].to_numpy(dtype=float)

    affected_values = np.full(len(raw), "", dtype=object)
    evidence_values = np.full(len(raw), "", dtype=object)
    for i in flagged_pos:
        seen: list[str] = []
        for detector, source in sources.items():
            if not trig[detector][i]:
                continue
            for name in str(source[i]).split("|"):
                if name and name not in seen:
                    seen.append(name)
        affected_values[i] = "|".join(seen)
        evidence_values[i] = _evidence_payload(
            raw_np[i],
            norm_np[i],
            [d for d in DETECTORS if trig[d][i]],
            affected_values[i],
        )
    affected = pd.Series(affected_values, index=raw.index, dtype=str)
    evidence = pd.Series(evidence_values, index=raw.index, dtype=str)

    out = pd.DataFrame(index=raw.index)
    out["profile"] = labels.astype(str)
    for detector in DETECTORS:
        out[SCORE_COLUMNS[detector]] = norm_all[detector]
    out["combined_score"] = combined
    out["severity"] = severity
    out["triggered_detectors"] = triggered
    out["affected_variables"] = affected
    out["evidence"] = evidence
    return out
