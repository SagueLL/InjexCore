"""Detector A: robust-z scoring, breach flags, sensor-level evidence."""

from __future__ import annotations

import numpy as np
from src.intelligence.anomaly import statistical
from src.intelligence.anomaly.policy import AnomalyPolicy

_POLICY = AnomalyPolicy.model_validate({})


def test_planted_spike_names_right_sensor(
    labeled_frame, groups, baselines_factory
) -> None:
    df, labels, train_mask = labeled_frame(n_rows=100, train_fraction=0.5)
    sensors = [c for c in groups.process if c in df.columns][:5]
    baselines = baselines_factory(df, labels, train_mask, sensors)

    target = sensors[2]
    spike_row = df.index[-1]
    df.loc[spike_row, target] = 1e4

    result, _ = statistical.score(df, labels, baselines, _POLICY)
    assert result.raw.loc[spike_row] > 100  # enormous robust z
    assert result.affected.loc[spike_row].split("|")[0] == target
    assert result.breaches.loc[spike_row] >= 1
    assert "profile_a" in result.supported_profiles


def test_normal_rows_have_low_scores(labeled_frame, groups, baselines_factory) -> None:
    df, labels, train_mask = labeled_frame(n_rows=100, train_fraction=0.5)
    sensors = [c for c in groups.process if c in df.columns][:5]
    baselines = baselines_factory(df, labels, train_mask, sensors)
    result, _ = statistical.score(df, labels, baselines, _POLICY)
    # Gaussian noise scored against its own distribution: well under z=3.5
    # for the bulk, so affected lists stay empty almost everywhere.
    assert float(result.raw.median()) < 3.5
    assert (result.affected == "").mean() > 0.9


def test_profile_without_baselines_stays_nan(
    labeled_frame, groups, baselines_factory
) -> None:
    df, labels, train_mask = labeled_frame(n_rows=100, n_profiles=2, train_fraction=0.5)
    sensors = [c for c in groups.process if c in df.columns][:5]
    baselines = baselines_factory(df, labels, train_mask, sensors)
    baselines = baselines[baselines["profile"] == "profile_a"]

    result, _ = statistical.score(df, labels, baselines, _POLICY)
    b_rows = labels == "profile_b"
    assert result.raw.loc[b_rows].isna().all()
    assert result.raw.loc[~b_rows].notna().all()
    assert result.supported_profiles == ["profile_a"]


def test_collapsed_iqr_falls_back_to_std(
    labeled_frame, groups, baselines_factory
) -> None:
    df, labels, train_mask = labeled_frame(n_rows=100, train_fraction=0.5)
    sensors = [c for c in groups.process if c in df.columns][:2]
    baselines = baselines_factory(df, labels, train_mask, sensors)
    baselines.loc[baselines["sensor"] == sensors[0], "iqr"] = 0.0  # collapsed

    result, _ = statistical.score(df, labels, baselines, _POLICY)
    assert result.raw.notna().all()
    assert np.isfinite(result.raw).all()


def test_missing_percentile_column_skips_detector(
    labeled_frame, groups, baselines_factory
) -> None:
    df, labels, train_mask = labeled_frame(n_rows=60, train_fraction=0.5)
    sensors = [c for c in groups.process if c in df.columns][:3]
    baselines = baselines_factory(df, labels, train_mask, sensors).drop(columns=["p95"])
    result, findings = statistical.score(df, labels, baselines, _POLICY)
    assert result.raw.isna().all()
    assert any(f.finding_type == "baseline_percentile_missing" for f in findings)
