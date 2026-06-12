"""Detector D: deterministic Isolation Forest, transparent raw scores."""

from __future__ import annotations

import pandas as pd
from src.intelligence.anomaly import iforest
from src.intelligence.anomaly.policy import AnomalyPolicy

_POLICY = AnomalyPolicy.model_validate({})


def _train_frame(labeled_frame, groups, n_rows: int = 100):
    df, labels, train_mask = labeled_frame(n_rows=n_rows, train_fraction=0.5)
    sensors = [c for c in groups.process if c in df.columns][:5]
    return df, sensors, df.loc[train_mask.to_numpy(), sensors]


def test_same_seed_identical_scores(labeled_frame, groups) -> None:
    df, sensors, train_rows = _train_frame(labeled_frame, groups)
    model_a, _, _ = iforest.fit_profile(train_rows, _POLICY, "profile_a")
    model_b, _, _ = iforest.fit_profile(train_rows, _POLICY, "profile_a")
    pd.testing.assert_series_equal(
        iforest.score(df[sensors], model_a), iforest.score(df[sensors], model_b)
    )


def test_planted_outlier_scores_higher(labeled_frame, groups) -> None:
    df, sensors, train_rows = _train_frame(labeled_frame, groups)
    model, _, _ = iforest.fit_profile(train_rows, _POLICY, "profile_a")
    outlier_row = df.index[-1]
    df.loc[outlier_row, sensors] = 1e4
    scores = iforest.score(df[sensors], model)
    assert scores.loc[outlier_row] > scores.drop(outlier_row).max()


def test_fit_records_seed_in_finding(labeled_frame, groups) -> None:
    _, _, train_rows = _train_frame(labeled_frame, groups)
    _, findings, _ = iforest.fit_profile(train_rows, _POLICY, "profile_a")
    fit = [f for f in findings if f.finding_type == "profile_iforest_fit"][0]
    assert fit.evidence["random_state"] == 42


def test_constant_features_skip_profile(labeled_frame, groups) -> None:
    _, sensors, train_rows = _train_frame(labeled_frame, groups)
    train_rows = train_rows.copy()
    for s in sensors:
        train_rows[s] = 1.0
    model, _, skip = iforest.fit_profile(train_rows, _POLICY, "profile_a")
    assert model is None
    assert skip.startswith("insufficient_features")
