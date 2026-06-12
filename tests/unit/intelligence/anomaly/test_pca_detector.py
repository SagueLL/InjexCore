"""Detector C: train-percentile thresholds over a persisted pca run."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from src.intelligence.anomaly import pca_detector
from src.intelligence.anomaly.policy import AnomalyPolicy

_POLICY = AnomalyPolicy.model_validate({})


def _fake_pca_run(tmp_path: Path, index: pd.DatetimeIndex) -> Path:
    """A minimal completed pca run: one profile's scores + contributions."""
    n = len(index)
    rng = np.random.default_rng(3)
    scores = pd.DataFrame(
        {
            "timestamp": index,
            "t2": rng.uniform(0.0, 1.0, n),
            "q_spe": rng.uniform(0.0, 1.0, n),
            "is_train": [1] * (n // 2) + [0] * (n - n // 2),
        }
    )
    # Planted validation outlier: enormous Q on the last row.
    scores.loc[n - 1, "q_spe"] = 50.0
    contributions = pd.DataFrame(
        {
            "timestamp": index,
            "sensor_a": rng.uniform(0.0, 0.5, n),
            "sensor_b": rng.uniform(0.0, 0.5, n),
        }
    )
    contributions.loc[n - 1, "sensor_b"] = 49.0  # dominates the planted Q

    run = tmp_path / "runs" / "fake"
    pdir = run / "scores" / "profile_a"
    pdir.mkdir(parents=True)
    scores.to_parquet(pdir / "scores.parquet", index=False)
    contributions.to_parquet(pdir / "contributions.parquet", index=False)
    return run


def test_thresholds_are_train_percentiles(tmp_path: Path) -> None:
    index = pd.date_range("2025-01-01", periods=100, freq="60s", name="timestamp")
    run = _fake_pca_run(tmp_path, index)
    result, _ = pca_detector.score(run, index, _POLICY)
    limits = result.thresholds["profile_a"]
    scores = pd.read_parquet(run / "scores" / "profile_a" / "scores.parquet")
    train = scores[scores["is_train"] == 1]
    assert limits.q_threshold == float(np.nanpercentile(train["q_spe"], 99.0))
    assert limits.t2_threshold == float(np.nanpercentile(train["t2"], 99.0))
    assert limits.n_train == 50


def test_planted_outlier_exceeds_q_threshold_and_is_attributed(
    tmp_path: Path,
) -> None:
    index = pd.date_range("2025-01-01", periods=100, freq="60s", name="timestamp")
    run = _fake_pca_run(tmp_path, index)
    result, _ = pca_detector.score(run, index, _POLICY)
    outlier = index[-1]
    assert result.q_raw.loc[outlier] > result.thresholds["profile_a"].q_threshold
    assert result.affected.loc[outlier].split("|")[0] == "sensor_b"


def test_missing_scores_dir_reports_finding(tmp_path: Path) -> None:
    index = pd.date_range("2025-01-01", periods=10, freq="60s", name="timestamp")
    result, findings = pca_detector.score(tmp_path / "empty_run", index, _POLICY)
    assert result.q_raw.isna().all()
    assert any(f.finding_type == "no_pca_scores_found" for f in findings)


def test_index_mismatch_skips_profile(tmp_path: Path) -> None:
    index = pd.date_range("2025-01-01", periods=100, freq="60s", name="timestamp")
    run = _fake_pca_run(tmp_path, index)
    other_index = pd.date_range("2026-01-01", periods=100, freq="60s")
    result, findings = pca_detector.score(run, other_index, _POLICY)
    assert "profile_a" in result.skipped
    assert any(f.finding_type == "pca_scores_index_mismatch" for f in findings)
