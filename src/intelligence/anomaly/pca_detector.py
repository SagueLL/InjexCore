"""Detector C — T²/Q thresholds over the persisted PCA Intelligence run.

Consumes the per-profile ``scores.parquet`` and ``contributions.parquet``
that a completed pca run persisted — no model is reloaded or refitted here.
Thresholds are empirical percentiles of the *training* scores (``is_train``
flag in the parquet), never of the full dataset. Affected variables come
from the per-feature reconstruction contributions, which sum exactly to the
Q statistic.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.intelligence._common.reporting import Finding, Severity
from src.intelligence.anomaly.policy import AnomalyPolicy
from src.intelligence.pca import io as pca_io

CHECK = "anomaly_pca"


@dataclass(frozen=True)
class PcaThresholds:
    """Train-percentile control limits for one profile."""

    profile: str
    t2_threshold: float
    q_threshold: float
    n_train: int


@dataclass(frozen=True)
class PcaDetectorResult:
    """Full-index detector outputs (NaN where unsupported)."""

    t2_raw: pd.Series
    q_raw: pd.Series
    affected: pd.Series  # top Q contributors, "" where not computed
    thresholds: dict[str, PcaThresholds]
    skipped: dict[str, str]  # profile -> reason


def fit_thresholds(
    scores: pd.DataFrame, policy: AnomalyPolicy, profile: str
) -> PcaThresholds | None:
    """Empirical train-percentile thresholds; None when no train scores."""
    train = scores[scores["is_train"] == 1]
    if train.empty:
        return None
    pp = policy.pca_detector
    return PcaThresholds(
        profile=profile,
        t2_threshold=float(np.nanpercentile(train["t2"], pp.t2_threshold_percentile)),
        q_threshold=float(np.nanpercentile(train["q_spe"], pp.q_threshold_percentile)),
        n_train=int(len(train)),
    )


def _top_contributors(contributions: pd.DataFrame, top_k: int) -> pd.Series:
    arr = contributions.to_numpy()
    order = np.argsort(-np.nan_to_num(arr, nan=-np.inf), axis=1)[:, :top_k]
    names = np.array(contributions.columns)
    values = ["|".join(names[row]) for row in order]
    return pd.Series(values, index=contributions.index, dtype=str)


def score(
    pca_run_dir: Path,
    index: pd.Index,
    policy: AnomalyPolicy,
) -> tuple[PcaDetectorResult, list[Finding]]:
    """Load every profile's persisted pca scores and derive raw T²/Q series."""
    findings: list[Finding] = []
    t2_raw = pd.Series(np.nan, index=index)
    q_raw = pd.Series(np.nan, index=index)
    affected = pd.Series("", index=index, dtype=str)
    thresholds: dict[str, PcaThresholds] = {}
    skipped: dict[str, str] = {}

    scores_root = pca_run_dir / "scores"
    profile_dirs = sorted(scores_root.iterdir()) if scores_root.is_dir() else []
    if not profile_dirs:
        findings.append(
            Finding(
                check=CHECK,
                severity=Severity.IMPORTANT,
                finding_type="no_pca_scores_found",
                action_taken="skip_detector",
                evidence={"pca_run": str(pca_run_dir)},
            )
        )
        return (
            PcaDetectorResult(t2_raw, q_raw, affected, thresholds, skipped),
            findings,
        )

    for pdir in profile_dirs:
        profile = pdir.name
        scores = pd.read_parquet(pdir / pca_io.SCORES_FILE)
        scores["timestamp"] = pd.to_datetime(scores["timestamp"], errors="coerce")
        scores = scores.set_index("timestamp")

        missing = scores.index.difference(index)
        if len(missing):
            skipped[profile] = f"index_mismatch ({len(missing)} unmatched rows)"
            findings.append(
                Finding(
                    check=CHECK,
                    severity=Severity.IMPORTANT,
                    finding_type="pca_scores_index_mismatch",
                    column=profile,
                    count=int(len(missing)),
                    action_taken="skip_profile",
                )
            )
            continue

        limits = fit_thresholds(scores, policy, profile)
        if limits is None:
            skipped[profile] = "no_train_scores"
            findings.append(
                Finding(
                    check=CHECK,
                    severity=Severity.IMPORTANT,
                    finding_type="profile_no_train_scores",
                    column=profile,
                    action_taken="skip_profile",
                )
            )
            continue

        t2_raw.loc[scores.index] = scores["t2"].to_numpy()
        q_raw.loc[scores.index] = scores["q_spe"].to_numpy()
        thresholds[profile] = limits

        contributions = pd.read_parquet(pdir / pca_io.CONTRIBUTIONS_FILE)
        contributions["timestamp"] = pd.to_datetime(
            contributions["timestamp"], errors="coerce"
        )
        contributions = contributions.set_index("timestamp")
        affected.loc[contributions.index] = _top_contributors(
            contributions, policy.pca_detector.top_k_variables
        )

    return (
        PcaDetectorResult(
            t2_raw=t2_raw,
            q_raw=q_raw,
            affected=affected,
            thresholds=thresholds,
            skipped=skipped,
        ),
        findings,
    )
