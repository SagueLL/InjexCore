"""Detector D — Isolation Forest per profile, deterministic and transparent.

Fitted on the training rows only with a pinned ``random_state``; scoring
exposes ``-score_samples`` directly (higher = more anomalous). No
feature-level attribution is produced — Isolation Forest cannot support one
reliably, and inventing root causes would be fabrication. Sensor-level
evidence comes from the interpretable detectors instead.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sklearn.ensemble import IsolationForest

from src.intelligence._common.reporting import Finding, Severity
from src.intelligence.anomaly._matrix import apply_imputation, prepare_train_matrix
from src.intelligence.anomaly.policy import AnomalyPolicy

CHECK = "anomaly_iforest"


@dataclass(frozen=True)
class IForestModel:
    """Fitted per-profile Isolation Forest + its imputation reference."""

    profile: str
    features: list[str]
    medians: pd.Series
    estimator: IsolationForest
    n_train: int


def fit_profile(
    X_train: pd.DataFrame, policy: AnomalyPolicy, profile: str
) -> tuple[IForestModel | None, list[Finding], str | None]:
    """Fit the Isolation Forest for one profile on its training rows."""
    findings: list[Finding] = []
    prepared, skip_reason = prepare_train_matrix(
        X_train, min_non_null_fraction=policy.features.min_non_null_fraction
    )
    if prepared is None:
        return None, findings, skip_reason

    ip = policy.isolation_forest
    estimator = IsolationForest(
        n_estimators=ip.n_estimators,
        max_samples=ip.max_samples,
        random_state=ip.random_state,
    )
    estimator.fit(prepared.X)

    model = IForestModel(
        profile=profile,
        features=prepared.features,
        medians=prepared.medians,
        estimator=estimator,
        n_train=int(len(prepared.X)),
    )
    findings.append(
        Finding(
            check=CHECK,
            severity=Severity.NORMAL,
            finding_type="profile_iforest_fit",
            column=profile,
            action_taken="fit_on_train",
            evidence={
                "n_train": model.n_train,
                "n_features": len(model.features),
                "n_estimators": ip.n_estimators,
                "random_state": ip.random_state,
            },
        )
    )
    return model, findings, None


def score(df_rows: pd.DataFrame, model: IForestModel) -> pd.Series:
    """Raw anomaly score: ``-score_samples`` (higher = more anomalous)."""
    X = apply_imputation(df_rows, model.features, model.medians)
    return pd.Series(-model.estimator.score_samples(X), index=df_rows.index)
