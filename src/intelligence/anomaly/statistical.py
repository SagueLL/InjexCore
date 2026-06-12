"""Detector A — statistical deviation against the behaviour baselines.

Model-free: the per-(profile, sensor) baseline table fitted by Behaviour
Intelligence on the training window *is* the model. Per row:

* robust z per sensor: ``|x - median| / (iqr / 1.349)`` (std fallback when
  the IQR collapses; sensors with no usable scale are skipped per profile);
* breach flags against the configured baseline percentiles (p05/p95);
* raw score = the worst robust z across the profile's sensors;
* affected variables = the top-k sensors whose robust z clears the
  configured threshold — directly interpretable sensor-level evidence.

Profiles without baselines stay NaN and are reported as unsupported.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.intelligence._common.reporting import Finding, Severity
from src.intelligence.anomaly.policy import AnomalyPolicy

CHECK = "anomaly_statistical"
# IQR -> sigma under normality; the conventional robust-z denominator.
_IQR_TO_SIGMA = 1.349
_SCALE_EPS = 1e-9


@dataclass(frozen=True)
class StatisticalResult:
    """Full-index detector outputs (NaN where unsupported)."""

    raw: pd.Series  # max |robust z| across the profile's sensors
    breaches: pd.Series  # count of percentile breaches (float; NaN unsupported)
    affected: pd.Series  # "sensor_a|sensor_b" top-k above threshold, else ""
    supported_profiles: list[str]
    skipped: dict[str, str]  # profile -> reason


def _top_affected(
    z: np.ndarray, sensors: list[str], threshold: float, top_k: int
) -> list[str]:
    """Per-row pipe-joined top-k sensors whose robust z clears the threshold."""
    filled = np.nan_to_num(z, nan=-np.inf)
    order = np.argsort(-filled, axis=1)[:, :top_k]
    names = np.array(sensors)
    out: list[str] = []
    for row_order, row_z in zip(order, filled, strict=True):
        picks = [names[j] for j in row_order if row_z[j] >= threshold]
        out.append("|".join(picks))
    return out


def score(
    df: pd.DataFrame,
    labels: pd.Series,
    baselines: pd.DataFrame,
    policy: AnomalyPolicy,
) -> tuple[StatisticalResult, list[Finding]]:
    """Score every row against its profile's baselines."""
    sp = policy.statistical
    findings: list[Finding] = []
    raw = pd.Series(np.nan, index=df.index)
    breaches = pd.Series(np.nan, index=df.index)
    affected = pd.Series("", index=df.index, dtype=str)
    supported: list[str] = []
    skipped: dict[str, str] = {}

    for pcol in (sp.lower_percentile, sp.upper_percentile):
        if pcol not in baselines.columns:
            findings.append(
                Finding(
                    check=CHECK,
                    severity=Severity.IMPORTANT,
                    finding_type="baseline_percentile_missing",
                    column=pcol,
                    action_taken="skip_detector",
                    evidence={"available": list(baselines.columns)},
                )
            )
            return (
                StatisticalResult(raw, breaches, affected, [], {}),
                findings,
            )

    for profile, base in baselines.groupby("profile", sort=True):
        profile = str(profile)
        mask = (labels == profile).to_numpy()
        if not mask.any():
            continue
        base = base.set_index("sensor")
        sensors_present = [s for s in base.index if s in df.columns]

        scale = base["iqr"] / _IQR_TO_SIGMA
        scale = scale.where(scale >= _SCALE_EPS, base["std"])
        usable = [s for s in sensors_present if scale.loc[s] >= _SCALE_EPS]
        if not usable:
            skipped[profile] = "no_usable_sensors (all scales collapsed)"
            findings.append(
                Finding(
                    check=CHECK,
                    severity=Severity.IMPORTANT,
                    finding_type="profile_no_usable_sensors",
                    column=profile,
                    action_taken="skip_profile",
                )
            )
            continue

        X = df.loc[mask, usable].astype(float)
        z = ((X - base.loc[usable, "median"]).abs() / scale.loc[usable]).to_numpy()
        breach = (base.loc[usable, sp.lower_percentile] > X) | (
            base.loc[usable, sp.upper_percentile] < X
        )

        raw.loc[mask] = np.nanmax(z, axis=1)
        breaches.loc[mask] = breach.sum(axis=1).astype(float)
        affected.loc[mask] = _top_affected(
            z, usable, sp.robust_z_threshold, sp.top_k_variables
        )
        supported.append(profile)

    return (
        StatisticalResult(
            raw=raw,
            breaches=breaches,
            affected=affected,
            supported_profiles=supported,
            skipped=skipped,
        ),
        findings,
    )
