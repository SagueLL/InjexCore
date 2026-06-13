"""Univariate drift: train-only references, metrics, views, gating."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd
from src.intelligence.drift import univariate as uni
from src.intelligence.drift.policy import GLOBAL_SCOPE_KEY, DriftPolicy

Frame = tuple[pd.DataFrame, np.ndarray, np.ndarray]


def _hourly_policy(policy_factory: Callable[..., DriftPolicy]) -> DriftPolicy:
    return policy_factory(
        profiles={"min_samples_per_profile": 50},
        windows={"granularity": "hourly", "min_rows_per_window": 20},
    )


def test_references_use_train_rows_only(
    labeled_frame: Frame, policy_factory: Callable[..., DriftPolicy]
) -> None:
    df, profiles, train = labeled_frame
    policy = _hourly_policy(policy_factory)
    refs, _ = uni.train_references(df, ["s1"], profiles, train, policy)
    mutated = df.copy()
    mutated.loc[~pd.Series(train, index=df.index), "s1"] = 1e6
    refs_after, _ = uni.train_references(mutated, ["s1"], profiles, train, policy)
    key = ("s1", GLOBAL_SCOPE_KEY)
    assert refs[key].mean == refs_after[key].mean
    assert refs[key].std == refs_after[key].std


def test_global_and_per_profile_scopes(
    labeled_frame: Frame, policy_factory: Callable[..., DriftPolicy]
) -> None:
    df, profiles, train = labeled_frame
    policy = _hourly_policy(policy_factory)
    refs, unsupported = uni.train_references(df, ["s1", "s2"], profiles, train, policy)
    scope_keys = {k for (_, k) in refs}
    assert scope_keys == {GLOBAL_SCOPE_KEY, "stopped", "mid_production"}
    assert not unsupported


def test_mean_shift_detected_in_validation_windows(
    labeled_frame: Frame, policy_factory: Callable[..., DriftPolicy]
) -> None:
    df, profiles, train = labeled_frame
    df = df.copy()
    df.loc[~pd.Series(train, index=df.index), "s1"] += 5.0
    policy = _hourly_policy(policy_factory)
    refs, _ = uni.train_references(df, ["s1"], profiles, train, policy)
    rows, _ = uni.score_windows(df, ["s1"], profiles, refs, policy, view="raw")
    mean_shift = rows[
        (rows.metric == "mean_shift") & (rows.profile == GLOBAL_SCOPE_KEY)
    ].set_index("window_start")["value"]
    train_end = df.index[train].max().floor("1h")
    assert mean_shift[mean_shift.index <= train_end].max() < 1.0
    assert mean_shift[mean_shift.index > train_end].min() > 3.0


def test_zero_rate_missingness_and_unique_collapse(
    labeled_frame: Frame, policy_factory: Callable[..., DriftPolicy]
) -> None:
    df, profiles, train = labeled_frame
    df = df.copy()
    validation = (~pd.Series(train, index=df.index)).to_numpy()
    df.loc[validation, "s1"] = 0.0  # flatline zero in validation
    half_outage = validation & (np.arange(len(df)) % 2 == 0)
    df.loc[half_outage, "s2"] = np.nan  # 50% outage in validation
    policy = _hourly_policy(policy_factory)
    refs, _ = uni.train_references(df, ["s1", "s2"], profiles, train, policy)
    rows, _ = uni.score_windows(df, ["s1", "s2"], profiles, refs, policy, view="raw")
    last = rows[rows.window_start == rows.window_start.max()]
    s1 = last[(last.entity == "s1") & (last.profile == GLOBAL_SCOPE_KEY)]
    assert s1.set_index("metric")["value"]["zero_rate_shift"] > 0.9
    assert s1.set_index("metric")["value"]["unique_value_collapse"] == 1.0
    s2 = last[(last.entity == "s2") & (last.profile == GLOBAL_SCOPE_KEY)]
    assert s2.set_index("metric")["value"]["missingness_shift"] > 0.4


def test_min_rows_gating_skips_thin_windows(
    labeled_frame: Frame, policy_factory: Callable[..., DriftPolicy]
) -> None:
    df, profiles, train = labeled_frame
    policy = policy_factory(
        profiles={"min_samples_per_profile": 50},
        windows={"granularity": "hourly", "min_rows_per_window": 1000},
    )
    refs, _ = uni.train_references(df, ["s1"], profiles, train, policy)
    rows, _ = uni.score_windows(df, ["s1"], profiles, refs, policy, view="raw")
    assert len(rows) == 0


def test_exclusion_mask_removes_cells_and_reports_fully_masked(
    labeled_frame: Frame, policy_factory: Callable[..., DriftPolicy]
) -> None:
    df, profiles, train = labeled_frame
    df = df.copy()
    validation = ~pd.Series(train, index=df.index)
    df.loc[validation, "s1"] += 50.0  # raw drift, entirely on masked rows
    policy = _hourly_policy(policy_factory)
    refs, _ = uni.train_references(df, ["s1"], profiles, train, policy)
    mask = pd.DataFrame(False, index=df.index, columns=["s1"])
    mask.loc[validation, "s1"] = True

    raw_rows, _ = uni.score_windows(df, ["s1"], profiles, refs, policy, view="raw")
    healthy_rows, unsupported = uni.score_windows(
        df, ["s1"], profiles, refs, policy, view="healthy_only", exclusion_mask=mask
    )
    train_end = df.index[train].max().floor("1h")
    raw_validation = raw_rows[
        (raw_rows.metric == "mean_shift") & (raw_rows.window_start > train_end)
    ]
    assert raw_validation["value"].min() > 10.0  # raw view sees the shift
    assert (healthy_rows.window_start <= train_end).all()  # masked windows gone
    assert any(u["reason"].startswith("all_rows_health_excluded") for u in unsupported)
    assert all(u["view"] == "healthy_only" for u in unsupported)
