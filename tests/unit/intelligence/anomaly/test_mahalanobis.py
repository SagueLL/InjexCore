"""Detector B: regularized covariance, contribution arithmetic, persistence."""

from __future__ import annotations

import numpy as np
import pandas as pd
from src.intelligence.anomaly import mahalanobis
from src.intelligence.anomaly.policy import AnomalyPolicy

_POLICY = AnomalyPolicy.model_validate({})


def _train_frame(labeled_frame, groups, n_rows: int = 100):
    df, labels, train_mask = labeled_frame(n_rows=n_rows, train_fraction=0.5)
    sensors = [c for c in groups.process if c in df.columns][:5]
    train_rows = df.loc[train_mask.to_numpy(), sensors]
    return df, sensors, train_rows


def test_near_singular_data_still_fits(labeled_frame, groups) -> None:
    df, sensors, train_rows = _train_frame(labeled_frame, groups)
    train_rows = train_rows.copy()
    train_rows[sensors[1]] = train_rows[sensors[0]]  # duplicated column
    model, _, skip = mahalanobis.fit_profile(train_rows, _POLICY, "profile_a")
    assert skip is None and model is not None
    assert np.isfinite(model.precision).all()


def test_contributions_sum_to_d2(labeled_frame, groups) -> None:
    df, sensors, train_rows = _train_frame(labeled_frame, groups)
    model, _, _ = mahalanobis.fit_profile(train_rows, _POLICY, "profile_a")
    d2, contributions = mahalanobis.score(df[sensors], model)
    np.testing.assert_allclose(
        contributions.sum(axis=1).clip(lower=0).to_numpy(),
        d2.to_numpy(),
        rtol=1e-8,
        atol=1e-10,
    )


def test_planted_outlier_scores_high_and_is_attributed(labeled_frame, groups) -> None:
    df, sensors, train_rows = _train_frame(labeled_frame, groups)
    model, _, _ = mahalanobis.fit_profile(train_rows, _POLICY, "profile_a")
    outlier_row = df.index[-1]
    df.loc[outlier_row, sensors[0]] = 1e4

    d2, contributions = mahalanobis.score(df[sensors], model)
    assert d2.loc[outlier_row] > 100 * d2.drop(outlier_row).median()
    affected = mahalanobis.top_affected(contributions, top_k=2)
    assert affected.loc[outlier_row].split("|")[0] == sensors[0]


def test_json_roundtrip_reproduces_scores(labeled_frame, groups) -> None:
    df, sensors, train_rows = _train_frame(labeled_frame, groups)
    model, _, _ = mahalanobis.fit_profile(train_rows, _POLICY, "profile_a")
    reloaded = mahalanobis.MahalanobisModel.from_json_dict(model.to_json_dict())
    d2_a, _ = mahalanobis.score(df[sensors], model)
    d2_b, _ = mahalanobis.score(df[sensors], reloaded)
    pd.testing.assert_series_equal(d2_a, d2_b)
    assert reloaded.estimator == "ledoit_wolf"


def test_all_constant_features_skip_profile(labeled_frame, groups) -> None:
    df, sensors, train_rows = _train_frame(labeled_frame, groups)
    train_rows = train_rows.copy()
    for s in sensors:
        train_rows[s] = 1.0
    model, _, skip = mahalanobis.fit_profile(train_rows, _POLICY, "profile_a")
    assert model is None
    assert skip.startswith("insufficient_features")
