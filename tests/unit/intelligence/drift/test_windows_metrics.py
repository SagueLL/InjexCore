"""Pure-numpy distribution metrics and window machinery."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from src.intelligence.drift import windows as win
from src.intelligence.drift.policy import WindowsPolicy


def test_window_starts_daily_and_hourly() -> None:
    idx = pd.DatetimeIndex(["2024-06-01 10:30", "2024-06-01 11:05", "2024-06-02 00:01"])
    daily = win.window_starts(idx, WindowsPolicy(granularity="daily"))
    assert list(daily) == [
        pd.Timestamp("2024-06-01"),
        pd.Timestamp("2024-06-01"),
        pd.Timestamp("2024-06-02"),
    ]
    hourly = win.window_starts(idx, WindowsPolicy(granularity="hourly"))
    assert hourly[0] == pd.Timestamp("2024-06-01 10:00")
    assert win.window_length(WindowsPolicy(granularity="hourly")) == pd.Timedelta("1h")


def test_ks_statistic_matches_hand_value() -> None:
    ref = np.array([1.0, 2.0, 3.0, 4.0])
    sample = np.array([3.0, 4.0, 5.0, 6.0])
    # ECDFs diverge most at x=2: ref 0.5 vs sample 0.0.
    assert win.ks_statistic(ref, sample) == pytest.approx(0.5)
    assert win.ks_statistic(ref, ref.copy()) == pytest.approx(0.0)


def test_wasserstein_matches_hand_value() -> None:
    ref = np.array([0.0, 1.0])
    sample = np.array([1.0, 2.0])  # every point moved by exactly 1
    assert win.wasserstein_1d(ref, sample) == pytest.approx(1.0)


def test_metrics_match_scipy_when_available() -> None:
    stats = pytest.importorskip("scipy.stats")
    rng = np.random.default_rng(42)
    ref = np.sort(rng.normal(0, 1, 2000))
    sample = rng.normal(0.4, 1.2, 700)
    assert win.ks_statistic(ref, sample) == pytest.approx(
        stats.ks_2samp(ref, sample).statistic
    )
    assert win.wasserstein_1d(ref, sample) == pytest.approx(
        stats.wasserstein_distance(ref, sample)
    )


def test_psi_zero_for_identical_and_positive_for_shifted() -> None:
    rng = np.random.default_rng(1)
    train = rng.normal(0, 1, 5000)
    edges = win.psi_bin_edges(train, 10)
    probs = win.bin_probabilities(train, edges)
    assert win.psi(probs, edges, train, 1e-4) == pytest.approx(0.0, abs=1e-6)
    shifted = rng.normal(1.5, 1, 1000)
    assert win.psi(probs, edges, shifted, 1e-4) > 0.5


def test_categorical_psi_and_total_variation() -> None:
    ref = {"a": 0.5, "b": 0.5}
    same = {"a": 50, "b": 50}
    assert win.categorical_psi(ref, same, 1e-4) == pytest.approx(0.0, abs=1e-6)
    assert win.total_variation(ref, same) == pytest.approx(0.0)
    flipped = {"a": 100}
    assert win.categorical_psi(ref, flipped, 1e-4) > 1.0
    assert win.total_variation(ref, flipped) == pytest.approx(0.5)


def test_downsample_sorted_is_deterministic_and_keeps_extremes() -> None:
    values = np.arange(10_000, dtype=float)
    a = win.downsample_sorted(values, 100)
    b = win.downsample_sorted(values, 100)
    assert np.array_equal(a, b)
    assert len(a) == 100
    assert a[0] == 0.0 and a[-1] == 9999.0
