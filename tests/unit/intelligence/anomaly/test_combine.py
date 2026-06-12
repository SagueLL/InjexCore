"""Combine: ECDF normalization, aggregation rules, severity mapping."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from src.intelligence.anomaly import combine
from src.intelligence.anomaly.policy import AnomalyPolicy

_POLICY = AnomalyPolicy.model_validate({})


def _raw_frame(n_rows: int = 200) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """One profile; smooth ramps on train rows so ECDF grids are stable."""
    index = pd.date_range("2025-01-01", periods=n_rows, freq="60s")
    rng = np.random.default_rng(11)
    raw = pd.DataFrame(
        {d: rng.uniform(0.0, 1.0, n_rows) for d in combine.DETECTORS}, index=index
    )
    labels = pd.Series("profile_a", index=index)
    train_mask = pd.Series(
        [True] * (n_rows // 2) + [False] * (n_rows - n_rows // 2), index=index
    )
    return raw, labels, train_mask


def _empty_affected(index: pd.Index) -> dict[str, pd.Series]:
    empty = pd.Series("", index=index, dtype=str)
    return {"statistical": empty, "mahalanobis": empty, "pca_q": empty}


def test_extreme_validation_value_becomes_anomaly() -> None:
    raw, labels, train_mask = _raw_frame()
    outlier = raw.index[-1]
    raw.loc[outlier] = 1e6  # beyond every train grid -> normalized 1.0

    model, _ = combine.fit(raw, labels, train_mask, _POLICY)
    scored = combine.apply(raw, labels, model, _POLICY, _empty_affected(raw.index))

    assert scored.loc[outlier, "combined_score"] == 1.0
    assert scored.loc[outlier, "severity"] == "anomaly"
    assert "statistical" in scored.loc[outlier, "triggered_detectors"]
    payload = json.loads(scored.loc[outlier, "evidence"])
    assert payload["detectors"]["statistical"]["normalized"] == 1.0


def test_bulk_rows_are_normal_with_max_rule() -> None:
    raw, labels, train_mask = _raw_frame()
    model, _ = combine.fit(raw, labels, train_mask, _POLICY)
    scored = combine.apply(raw, labels, model, _POLICY, _empty_affected(raw.index))
    assert (scored["severity"] == "normal").mean() > 0.95
    assert (scored["evidence"] == "").sum() == (
        ~scored["severity"].isin(["warning", "anomaly"])
    ).sum()


def test_weighted_mean_below_max() -> None:
    raw, labels, train_mask = _raw_frame()
    spike_row = raw.index[-1]
    raw.loc[spike_row, "statistical"] = 1e6  # only one detector extreme

    max_policy = _POLICY
    mean_policy = AnomalyPolicy.model_validate({"combine": {"method": "weighted_mean"}})

    model_max, _ = combine.fit(raw, labels, train_mask, max_policy)
    model_mean, _ = combine.fit(raw, labels, train_mask, mean_policy)
    scored_max = combine.apply(
        raw, labels, model_max, max_policy, _empty_affected(raw.index)
    )
    scored_mean = combine.apply(
        raw, labels, model_mean, mean_policy, _empty_affected(raw.index)
    )
    assert (
        scored_mean.loc[spike_row, "combined_score"]
        < scored_max.loc[spike_row, "combined_score"]
    )


def test_missing_detector_excluded_gracefully() -> None:
    raw, labels, train_mask = _raw_frame()
    raw["pca_q"] = np.nan
    raw["pca_t2"] = np.nan

    model, _ = combine.fit(raw, labels, train_mask, _POLICY)
    scored = combine.apply(raw, labels, model, _POLICY, _empty_affected(raw.index))
    assert "pca_q" not in model.grids["profile_a"]
    assert scored["pca_q_score"].isna().all()
    assert scored["combined_score"].notna().all()  # other detectors carry it


def test_unsupported_profile_rows_are_unscored() -> None:
    raw, labels, train_mask = _raw_frame()
    labels.iloc[-20:] = "profile_ghost"  # no train rows -> no grids
    model, _ = combine.fit(raw, labels, train_mask, _POLICY)
    scored = combine.apply(raw, labels, model, _POLICY, _empty_affected(raw.index))
    ghost = scored[scored["profile"] == "profile_ghost"]
    assert (ghost["severity"] == combine.SEVERITY_UNSCORED).all()
    assert ghost["combined_score"].isna().all()


def test_output_schema_exact() -> None:
    raw, labels, train_mask = _raw_frame()
    model, _ = combine.fit(raw, labels, train_mask, _POLICY)
    scored = combine.apply(raw, labels, model, _POLICY, _empty_affected(raw.index))
    assert list(scored.columns) == [
        "profile",
        "statistical_score",
        "mahalanobis_score",
        "pca_q_score",
        "pca_t2_score",
        "isolation_forest_score",
        "combined_score",
        "severity",
        "triggered_detectors",
        "affected_variables",
        "evidence",
    ]


def test_thresholds_fit_on_train_only() -> None:
    raw, labels, train_mask = _raw_frame()
    model_before, _ = combine.fit(raw, labels, train_mask, _POLICY)
    corrupted = raw.copy()
    corrupted.loc[~train_mask] = 1e9
    model_after, _ = combine.fit(corrupted, labels, train_mask, _POLICY)
    assert model_before.severity_thresholds == model_after.severity_thresholds
    for d in combine.DETECTORS:
        np.testing.assert_array_equal(
            model_before.grids["profile_a"][d], model_after.grids["profile_a"][d]
        )
