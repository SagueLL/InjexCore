"""Scoring with a fitted per-profile PCA model — no refitting.

Applies the persisted scaler + PCA to all rows of the model's profile
(training rows in-sample, validation rows out-of-sample, ``is_train``
preserved) and derives the multivariate diagnostics:

* ``t2`` — Hotelling T²: score distance inside the retained subspace,
  ``sum(t_j² / λ_j)`` over components with eigenvalue above a numeric floor.
* ``q_spe`` — Q-residual / squared prediction error: distance *from* the
  subspace, ``‖z - ẑ‖²`` in scaled space.
* per-feature reconstruction contributions — the squared residual per
  feature; rows sum exactly to ``q_spe``, so "which sensors drive the
  reconstruction error" stays arithmetically honest.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.intelligence.pca.model import ProfilePcaModel

# Components with eigenvalues below this are excluded from T² (a near-zero
# eigenvalue would turn numeric noise into a huge, meaningless score).
_EIGENVALUE_FLOOR = 1e-12


def score(
    df_profile: pd.DataFrame,
    model: ProfilePcaModel,
    *,
    is_train: pd.Series,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Score ``df_profile`` rows; returns ``(scores, contributions)``.

    ``df_profile`` must contain the model's feature columns; ``is_train``
    must align to its index. Missing values are filled with the *training*
    medians persisted on the model (leakage-safe by construction).
    """
    X = df_profile[model.features].astype(float).fillna(model.train_medians)
    Z = model.scaler.transform(X)
    T = model.pca.transform(Z)
    Z_hat = model.pca.inverse_transform(T)

    residual = Z - Z_hat
    contributions_values = residual**2
    q_spe = contributions_values.sum(axis=1)

    eigenvalues = np.asarray(model.pca.explained_variance_, dtype=float)
    valid = eigenvalues > _EIGENVALUE_FLOOR
    if valid.any():
        t2 = (T[:, valid] ** 2 / eigenvalues[valid]).sum(axis=1)
    else:
        t2 = np.full(len(X), np.nan)

    scores = pd.DataFrame(
        {f"pc_{j + 1}": T[:, j] for j in range(model.n_components)},
        index=df_profile.index,
    )
    scores["t2"] = t2
    scores["q_spe"] = q_spe
    scores["recon_error"] = np.sqrt(q_spe)
    scores["is_train"] = is_train.reindex(df_profile.index).astype("int8")

    contributions = pd.DataFrame(
        contributions_values, index=df_profile.index, columns=model.features
    )
    return scores, contributions
