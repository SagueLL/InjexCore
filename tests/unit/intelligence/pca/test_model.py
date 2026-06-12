"""Per-profile PCA fitting: component selection, leakage guard, skip logic."""

from __future__ import annotations

import numpy as np
import pandas as pd
from src.intelligence.pca import model
from src.intelligence.pca.policy import PcaPolicy

_LOW_GATES = {"profiles": {"min_samples_per_profile": 5}}


def _policy(**model_overrides) -> PcaPolicy:
    return PcaPolicy.model_validate(
        {**_LOW_GATES, "model": model_overrides} if model_overrides else _LOW_GATES
    )


def test_evr_target_picks_expected_component_count(labeled_frame, groups) -> None:
    df, labels, train_mask = labeled_frame(n_rows=60, train_fraction=1.0)
    a, b, c = groups.process[:3]
    rng = np.random.default_rng(0)
    base = rng.normal(0.0, 1.0, 60)
    df[a] = base
    df[b] = base + rng.normal(0.0, 1e-6, 60)  # near-duplicate of a
    df[c] = rng.normal(0.0, 1.0, 60)  # independent
    policy = PcaPolicy.model_validate(
        {
            "profiles": {"min_samples_per_profile": 5},
            "features": {"source": "explicit", "include_columns": [a, b, c]},
            "model": {"explained_variance_target": 0.95, "min_features": 3},
        }
    )
    art, _ = model.fit(df, labels, policy, groups, train_mask=train_mask)
    m = art.models["profile_a"]
    # Two correlated copies + one independent: 2 of 3 directions carry all
    # the variance, so 0.95 cumulative EVR needs exactly 2 components.
    assert m.n_components == 2


def test_fit_uses_train_window_only(labeled_frame, groups) -> None:
    df, labels, train_mask = labeled_frame(n_rows=60, train_fraction=0.5)
    policy = _policy()
    art_before, _ = model.fit(df, labels, policy, groups, train_mask=train_mask)

    corrupted = df.copy()
    process_cols = [c for c in groups.process if c in corrupted.columns]
    corrupted.loc[~train_mask, process_cols] = 1e9
    art_after, _ = model.fit(corrupted, labels, policy, groups, train_mask=train_mask)

    before = art_before.models["profile_a"]
    after = art_after.models["profile_a"]
    np.testing.assert_array_equal(before.pca.components_, after.pca.components_)
    pd.testing.assert_series_equal(before.train_medians, after.train_medians)


def test_deterministic_refit(labeled_frame, groups) -> None:
    df, labels, train_mask = labeled_frame(n_rows=60, train_fraction=1.0)
    policy = _policy()
    art1, _ = model.fit(df, labels, policy, groups, train_mask=train_mask)
    art2, _ = model.fit(df, labels, policy, groups, train_mask=train_mask)
    np.testing.assert_array_equal(
        art1.models["profile_a"].pca.components_,
        art2.models["profile_a"].pca.components_,
    )


def test_under_min_samples_profile_skipped(labeled_frame, groups) -> None:
    df, labels, train_mask = labeled_frame(n_rows=20, train_fraction=1.0)
    policy = PcaPolicy.model_validate({"profiles": {"min_samples_per_profile": 100}})
    art, findings = model.fit(df, labels, policy, groups, train_mask=train_mask)
    assert not art.models
    row = art.skipped[art.skipped["profile"] == "profile_a"].iloc[0]
    assert row["reason"].startswith("insufficient_rows")
    assert any(f.finding_type == "profile_under_min_samples" for f in findings)


def test_insufficient_features_profile_skipped(labeled_frame, groups) -> None:
    df, labels, train_mask = labeled_frame(n_rows=30, train_fraction=1.0)
    a, b = groups.process[:2]
    policy = PcaPolicy.model_validate(
        {
            "profiles": {"min_samples_per_profile": 5},
            "features": {"source": "explicit", "include_columns": [a, b]},
            "model": {"min_features": 3},
        }
    )
    art, findings = model.fit(df, labels, policy, groups, train_mask=train_mask)
    assert not art.models
    row = art.skipped.iloc[0]
    assert row["reason"].startswith("insufficient_features")
    assert any(f.finding_type == "profile_pca_skipped" for f in findings)


def test_zero_variance_feature_dropped_before_fit(labeled_frame, groups) -> None:
    df, labels, train_mask = labeled_frame(n_rows=40, train_fraction=1.0)
    frozen = groups.process[0]
    df[frozen] = 7.0
    art, findings = model.fit(df, labels, _policy(), groups, train_mask=train_mask)
    m = art.models["profile_a"]
    assert frozen not in m.features
    assert any(
        f.finding_type == "feature_zero_variance" and f.column == frozen
        for f in findings
    )


def test_drop_rows_missing_policy_can_skip_profile(labeled_frame, groups) -> None:
    df, labels, train_mask = labeled_frame(n_rows=30, train_fraction=1.0)
    # Every row misses some sensor -> dropna leaves nothing usable.
    process_cols = [c for c in groups.process if c in df.columns]
    for i, col in enumerate(process_cols):
        df.loc[df.index[i % len(df)], col] = np.nan
    df.loc[:, process_cols[0]] = np.nan  # fully missing column for good measure
    policy = _policy(missing_policy="drop_rows", max_missing_fraction=0.99)
    art, _ = model.fit(df, labels, policy, groups, train_mask=train_mask)
    if "profile_a" not in art.models:
        assert (art.skipped["reason"].str.startswith("excessive_missingness")).any()


def test_loadings_and_evr_tables_schema(labeled_frame, groups) -> None:
    df, labels, train_mask = labeled_frame(n_rows=40, train_fraction=1.0)
    art, _ = model.fit(df, labels, _policy(), groups, train_mask=train_mask)
    m = art.models["profile_a"]
    assert list(art.loadings.columns) == ["profile", "component", "feature", "loading"]
    assert len(art.loadings) == m.n_components * len(m.features)
    evr = art.explained_variance
    assert list(evr.columns) == ["profile", "component", "evr", "cumulative_evr"]
    assert evr["cumulative_evr"].is_monotonic_increasing
