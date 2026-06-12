"""PCA scoring: T²/Q diagnostics, contribution arithmetic, persistence."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from src.intelligence._common.persistence import load_model, save_model
from src.intelligence.pca import model, scoring
from src.intelligence.pca.policy import PcaPolicy

_POLICY = PcaPolicy.model_validate({"profiles": {"min_samples_per_profile": 5}})


def _fitted(labeled_frame, groups):
    df, labels, train_mask = labeled_frame(n_rows=60, train_fraction=0.5)
    art, _ = model.fit(df, labels, _POLICY, groups, train_mask=train_mask)
    return df, labels, train_mask, art.models["profile_a"]


def test_contributions_sum_to_q_spe(labeled_frame, groups) -> None:
    df, _, train_mask, m = _fitted(labeled_frame, groups)
    scores, contributions = scoring.score(df, m, is_train=train_mask)
    np.testing.assert_allclose(
        contributions.sum(axis=1).to_numpy(), scores["q_spe"].to_numpy()
    )


def test_t2_finite_and_nonnegative(labeled_frame, groups) -> None:
    df, _, train_mask, m = _fitted(labeled_frame, groups)
    scores, _ = scoring.score(df, m, is_train=train_mask)
    assert np.isfinite(scores["t2"]).all()
    assert (scores["t2"] >= 0).all()
    assert (scores["q_spe"] >= 0).all()


def test_planted_validation_outlier_has_high_q(labeled_frame, groups) -> None:
    df, _, train_mask, m = _fitted(labeled_frame, groups)
    outlier_row = df.index[-1]  # validation window
    df.loc[outlier_row, m.features[0]] = 1e4
    scores, contributions = scoring.score(df, m, is_train=train_mask)
    baseline_q = scores.loc[scores.index != outlier_row, "q_spe"].median()
    assert scores.loc[outlier_row, "q_spe"] > 100 * baseline_q
    # The planted sensor dominates the reconstruction error of that row.
    assert contributions.loc[outlier_row].idxmax() == m.features[0]


def test_is_train_flag_preserved(labeled_frame, groups) -> None:
    df, _, train_mask, m = _fitted(labeled_frame, groups)
    scores, _ = scoring.score(df, m, is_train=train_mask)
    assert int(scores["is_train"].sum()) == int(train_mask.sum())


def test_persistence_roundtrip_reproduces_scores(
    labeled_frame, groups, tmp_path: Path
) -> None:
    df, _, train_mask, m = _fitted(labeled_frame, groups)
    save_model(m.scaler, tmp_path / "scaler.joblib")
    save_model(m.pca, tmp_path / "pca.joblib")

    reloaded = model.ProfilePcaModel(
        profile=m.profile,
        features=m.features,
        scaler=load_model(tmp_path / "scaler.joblib"),
        pca=load_model(tmp_path / "pca.joblib"),
        n_components=m.n_components,
        explained_variance_ratio=m.explained_variance_ratio,
        train_medians=m.train_medians,
        n_train=m.n_train,
    )
    original, _ = scoring.score(df, m, is_train=train_mask)
    roundtrip, _ = scoring.score(df, reloaded, is_train=train_mask)
    pd.testing.assert_frame_equal(original, roundtrip)
