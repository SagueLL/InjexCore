"""Detector B — regularized Mahalanobis distance per profile.

Covariance is estimated on the training rows only, with Ledoit-Wolf
shrinkage by default so near-singular profiles (correlated or frozen
sensors) still yield a stable, invertible estimate. Per-variable evidence
uses the exact decomposition ``c_i = d_i * (P @ d)_i``, which sums to D²;
cross-terms can make individual contributions negative, so they are ranked
by absolute value and reported as *signed* contributions — defensible
arithmetic, not fake precision.

The fitted artifact is persisted as transparent JSON (mean + precision
matrix) rather than a pickle: a 17x17 matrix is diff-able and auditable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.covariance import LedoitWolf, ShrunkCovariance

from src.intelligence._common.reporting import Finding, Severity
from src.intelligence.anomaly._matrix import apply_imputation, prepare_train_matrix
from src.intelligence.anomaly.policy import AnomalyPolicy

CHECK = "anomaly_mahalanobis"


@dataclass(frozen=True)
class MahalanobisModel:
    """Fitted per-profile covariance artifact."""

    profile: str
    features: list[str]
    mean: np.ndarray
    precision: np.ndarray
    medians: pd.Series  # train-median imputation reference
    estimator: str
    n_train: int

    def to_json_dict(self) -> dict[str, Any]:
        """Transparent JSON persistence (mean + precision as nested lists)."""
        return {
            "component": "anomaly",
            "model_type": f"mahalanobis_{self.estimator}",
            "profile": self.profile,
            "features": self.features,
            "mean": self.mean.tolist(),
            "precision": self.precision.tolist(),
            "medians": {k: float(v) for k, v in self.medians.items()},
            "n_train": self.n_train,
        }

    @classmethod
    def from_json_dict(cls, d: dict[str, Any]) -> MahalanobisModel:
        return cls(
            profile=d["profile"],
            features=list(d["features"]),
            mean=np.asarray(d["mean"], dtype=float),
            precision=np.asarray(d["precision"], dtype=float),
            medians=pd.Series(d["medians"], dtype=float),
            estimator=str(d["model_type"]).removeprefix("mahalanobis_"),
            n_train=int(d["n_train"]),
        )


def fit_profile(
    X_train: pd.DataFrame, policy: AnomalyPolicy, profile: str
) -> tuple[MahalanobisModel | None, list[Finding], str | None]:
    """Fit the covariance artifact for one profile on its training rows."""
    findings: list[Finding] = []
    prepared, skip_reason = prepare_train_matrix(
        X_train, min_non_null_fraction=policy.features.min_non_null_fraction
    )
    if prepared is None:
        return None, findings, skip_reason

    mp = policy.mahalanobis
    estimator = (
        LedoitWolf()
        if mp.estimator == "ledoit_wolf"
        else ShrunkCovariance(shrinkage=mp.shrinkage)
    )
    estimator.fit(prepared.X)
    precision = np.asarray(estimator.precision_, dtype=float)
    if not np.isfinite(precision).all():
        return None, findings, "invalid_covariance (non-finite precision)"

    model = MahalanobisModel(
        profile=profile,
        features=prepared.features,
        mean=np.asarray(estimator.location_, dtype=float),
        precision=precision,
        medians=prepared.medians,
        estimator=mp.estimator,
        n_train=int(len(prepared.X)),
    )
    findings.append(
        Finding(
            check=CHECK,
            severity=Severity.NORMAL,
            finding_type="profile_covariance_fit",
            column=profile,
            action_taken="fit_on_train",
            evidence={
                "estimator": mp.estimator,
                "n_train": model.n_train,
                "n_features": len(model.features),
                "n_dropped_features": len(prepared.dropped),
            },
        )
    )
    return model, findings, None


def score(
    df_rows: pd.DataFrame, model: MahalanobisModel
) -> tuple[pd.Series, pd.DataFrame]:
    """D² plus signed per-variable contributions (rows sum to D²)."""
    X = apply_imputation(df_rows, model.features, model.medians)
    d = X.to_numpy() - model.mean
    pd_ = d @ model.precision
    contributions_values = d * pd_
    d2 = np.clip(contributions_values.sum(axis=1), 0.0, None)
    contributions = pd.DataFrame(
        contributions_values, index=df_rows.index, columns=model.features
    )
    return pd.Series(d2, index=df_rows.index), contributions


def top_affected(contributions: pd.DataFrame, top_k: int) -> pd.Series:
    """Per-row pipe-joined top-k features by |signed contribution|."""
    arr = np.abs(contributions.to_numpy())
    order = np.argsort(-np.nan_to_num(arr, nan=-np.inf), axis=1)[:, :top_k]
    names = np.array(contributions.columns)
    values = ["|".join(names[row]) for row in order]
    return pd.Series(values, index=contributions.index, dtype=str)
