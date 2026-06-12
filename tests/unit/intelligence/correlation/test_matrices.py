"""Per-profile correlation fitting: recovery, leakage guard, exclusions."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from src.intelligence._common.policy import GLOBAL_PROFILE
from src.intelligence.correlation import matrices
from src.intelligence.correlation.policy import CorrelationPolicy

_LOW_GATES = {
    "profiles": {"min_samples_per_profile": 5},
    "thresholds": {"min_valid_observations": 5},
}


def _pair_row(table: pd.DataFrame, a: str, b: str) -> pd.Series:
    lo, hi = sorted([a, b])
    return table[(table["feature_a"] == lo) & (table["feature_b"] == hi)].iloc[0]


def test_planted_pairs_recovered(labeled_frame, groups) -> None:
    df, labels, train_mask = labeled_frame(n_rows=30, train_fraction=1.0)
    a, b, c = groups.process[:3]
    base = np.linspace(0.0, 29.0, 30)
    df[a] = base
    df[b] = 2.0 * base + 1.0  # perfectly positive
    df[c] = -base  # perfectly negative
    policy = CorrelationPolicy.model_validate(_LOW_GATES)
    art, _ = matrices.fit(df, labels, policy, groups, train_mask=train_mask)
    assert _pair_row(art.correlations, a, b)["pearson"] == pytest.approx(1.0)
    assert _pair_row(art.correlations, a, c)["pearson"] == pytest.approx(-1.0)
    assert _pair_row(art.correlations, a, b)["spearman"] == pytest.approx(1.0)


def test_fit_uses_train_window_only(labeled_frame, groups) -> None:
    df, labels, train_mask = labeled_frame(n_rows=40, train_fraction=0.5)
    policy = CorrelationPolicy.model_validate(_LOW_GATES)
    art_before, _ = matrices.fit(df, labels, policy, groups, train_mask=train_mask)

    corrupted = df.copy()
    process_cols = [c for c in groups.process if c in corrupted.columns]
    corrupted.loc[~train_mask, process_cols] = 1e9
    art_after, _ = matrices.fit(
        corrupted, labels, policy, groups, train_mask=train_mask
    )
    pd.testing.assert_frame_equal(art_before.correlations, art_after.correlations)


def test_near_constant_feature_excluded(labeled_frame, groups) -> None:
    df, labels, train_mask = labeled_frame(n_rows=20, train_fraction=1.0)
    target = groups.process[0]
    df[target] = 42.0
    policy = CorrelationPolicy.model_validate(_LOW_GATES)
    art, _ = matrices.fit(df, labels, policy, groups, train_mask=train_mask)
    row = art.excluded[art.excluded["feature"] == target].iloc[0]
    assert row["reason"] == "near_constant"
    assert target not in set(art.correlations["feature_a"]) | set(
        art.correlations["feature_b"]
    )


def test_too_sparse_feature_excluded(labeled_frame, groups) -> None:
    df, labels, train_mask = labeled_frame(n_rows=20, train_fraction=1.0)
    target = groups.process[0]
    df.loc[df.index[:15], target] = np.nan  # 75% missing > 30% tolerance
    policy = CorrelationPolicy.model_validate(_LOW_GATES)
    art, _ = matrices.fit(df, labels, policy, groups, train_mask=train_mask)
    row = art.excluded[art.excluded["feature"] == target].iloc[0]
    assert row["reason"] == "too_sparse"


def test_under_min_samples_profile_skipped(labeled_frame, groups) -> None:
    df, labels, train_mask = labeled_frame(n_rows=20, train_fraction=1.0)
    policy = CorrelationPolicy.model_validate(
        {
            "profiles": {"min_samples_per_profile": 100},
            "thresholds": {"min_valid_observations": 5},
        }
    )
    art, findings = matrices.fit(df, labels, policy, groups, train_mask=train_mask)
    assert "profile_a" in art.profiles_skipped
    assert art.correlations.empty
    skip = [f for f in findings if f.finding_type == "profile_under_min_samples"]
    assert skip and skip[0].severity.value == "important"


def test_insufficient_joint_observations_yield_nan(labeled_frame, groups) -> None:
    df, labels, train_mask = labeled_frame(n_rows=20, train_fraction=1.0)
    a, b = groups.process[:2]
    # Disjoint missingness: only 4 joint observations, below min_periods=10.
    df.loc[df.index[:8], a] = np.nan
    df.loc[df.index[12:], b] = np.nan
    policy = CorrelationPolicy.model_validate(
        {
            "profiles": {"min_samples_per_profile": 5},
            "thresholds": {"min_valid_observations": 10, "max_missing_fraction": 0.5},
        }
    )
    art, _ = matrices.fit(df, labels, policy, groups, train_mask=train_mask)
    row = _pair_row(art.correlations, a, b)
    assert np.isnan(row["pearson"])
    assert row["n_valid"] == 4


def test_global_fallback_opt_in(labeled_frame, groups) -> None:
    df, labels, train_mask = labeled_frame(n_rows=30, n_profiles=2, train_fraction=1.0)
    base = {
        "profiles": {"min_samples_per_profile": 5, "global_fallback": True},
        "thresholds": {"min_valid_observations": 5},
    }
    art, _ = matrices.fit(
        df,
        labels,
        CorrelationPolicy.model_validate(base),
        groups,
        train_mask=train_mask,
    )
    assert GLOBAL_PROFILE in art.profiles_fitted

    base["profiles"]["global_fallback"] = False
    art_off, _ = matrices.fit(
        df,
        labels,
        CorrelationPolicy.model_validate(base),
        groups,
        train_mask=train_mask,
    )
    assert GLOBAL_PROFILE not in art_off.profiles_fitted
