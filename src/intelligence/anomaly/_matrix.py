"""Train-matrix preparation shared by the multivariate detectors.

Mahalanobis and Isolation Forest both need a complete numeric matrix:
per-profile feature eligibility (sparsity, near-constant variance) followed
by train-median imputation. Kept in one private helper so the two detectors
can never drift apart on what "eligible" means.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

_ZERO_VAR_EPS = 1e-9


@dataclass(frozen=True)
class PreparedMatrix:
    """Eligible features + imputed training matrix + imputation reference."""

    features: list[str]
    X: pd.DataFrame  # train rows, imputed, float
    medians: pd.Series  # train medians (leakage-safe imputation reference)
    dropped: dict[str, str]  # feature -> reason


def prepare_train_matrix(
    X_train: pd.DataFrame,
    *,
    min_non_null_fraction: float,
    min_features: int = 2,
) -> tuple[PreparedMatrix | None, str | None]:
    """Eligibility-gate and impute the training matrix for one profile.

    Returns ``(prepared, skip_reason)``; ``prepared`` is ``None`` when the
    profile cannot support a multivariate fit.
    """
    dropped: dict[str, str] = {}
    eligible: list[str] = []
    for feature in X_train.columns:
        s = X_train[feature]
        non_null = float(s.notna().mean()) if len(s) else 0.0
        if non_null < min_non_null_fraction:
            dropped[feature] = f"too_sparse (non_null={non_null:.3f})"
            continue
        std = float(s.std())
        if not np.isfinite(std) or std < _ZERO_VAR_EPS:
            dropped[feature] = f"near_constant (std={std:.3e})"
            continue
        eligible.append(feature)

    if len(eligible) < min_features:
        return None, f"insufficient_features ({len(eligible)})"

    X = X_train[eligible].astype(float)
    medians = X.median()
    return PreparedMatrix(
        features=eligible, X=X.fillna(medians), medians=medians, dropped=dropped
    ), None


def apply_imputation(
    df: pd.DataFrame, features: list[str], medians: pd.Series
) -> pd.DataFrame:
    """Project ``df`` onto the model's features, filling with train medians."""
    return df[features].astype(float).fillna(medians)
