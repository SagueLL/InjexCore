"""Behaviour Intelligence — per-profile statistical baselines."""

from __future__ import annotations

import pandas as pd
import pytest
from src.intelligence.behaviour import baselines
from src.intelligence.behaviour.policy import BehaviourPolicy

_MIN5 = BehaviourPolicy.model_validate({"profiles": {"min_samples_per_profile": 5}})
_SENSOR = "conditioner_inlet_temp"


def test_statistics_correct(behaviour_frame, groups) -> None:
    df = behaviour_frame(n_rows=5)
    df[_SENSOR] = [10.0, 20.0, 30.0, 40.0, 50.0]
    labels = pd.Series("running", index=df.index)
    art, _ = baselines.fit(
        df, labels, _MIN5, groups, train_mask=pd.Series(True, index=df.index)
    )
    row = art.table[
        (art.table["profile"] == "running") & (art.table["sensor"] == _SENSOR)
    ].iloc[0]
    assert row["count"] == 5
    assert row["mean"] == 30.0
    assert row["median"] == 30.0
    assert row["min"] == 10.0
    assert row["max"] == 50.0
    assert row["iqr"] == 20.0
    assert row["std"] == pytest.approx(15.8113883)
    assert row["p25"] == 20.0
    assert row["p75"] == 40.0
    assert row["p95"] == pytest.approx(48.0)


def test_fit_uses_train_window_only(behaviour_frame, groups) -> None:
    df = behaviour_frame(n_rows=10)
    # Train rows (first 5) = 100; validation rows = 0. Baseline must see 100 only.
    df[_SENSOR] = [100.0] * 5 + [0.0] * 5
    labels = pd.Series("running", index=df.index)
    train_mask = pd.Series([True] * 5 + [False] * 5, index=df.index)
    art, _ = baselines.fit(df, labels, _MIN5, groups, train_mask=train_mask)
    row = art.table[art.table["sensor"] == _SENSOR].iloc[0]
    assert row["mean"] == 100.0
    assert row["count"] == 5


def test_under_sized_profile_skipped(behaviour_frame, groups) -> None:
    df = behaviour_frame(n_rows=10)
    labels = pd.Series(["stopped"] * 2 + ["running"] * 8, index=df.index)
    art, findings = baselines.fit(
        df, labels, _MIN5, groups, train_mask=pd.Series(True, index=df.index)
    )
    skipped = [
        f
        for f in findings
        if f.finding_type == "profile_under_min_samples" and f.column == "stopped"
    ]
    assert skipped and skipped[0].severity.value == "important"
    assert "stopped" not in set(art.table["profile"])
    assert "running" in set(art.table["profile"])


def test_near_zero_variance_flagged(behaviour_frame, groups) -> None:
    df = behaviour_frame(n_rows=6)  # all sensors constant by default
    labels = pd.Series("running", index=df.index)
    _, findings = baselines.fit(
        df, labels, _MIN5, groups, train_mask=pd.Series(True, index=df.index)
    )
    assert any(f.finding_type == "near_zero_variance" for f in findings)


def test_table_has_expected_columns(behaviour_frame, groups) -> None:
    df = behaviour_frame(n_rows=6)
    labels = pd.Series("running", index=df.index)
    art, _ = baselines.fit(
        df, labels, _MIN5, groups, train_mask=pd.Series(True, index=df.index)
    )
    expected = {
        "profile",
        "sensor",
        "count",
        "mean",
        "median",
        "std",
        "min",
        "max",
        "iqr",
        "p05",
        "p25",
        "p50",
        "p75",
        "p95",
    }
    assert expected.issubset(set(art.table.columns))


def test_disabled_returns_empty(behaviour_frame, groups) -> None:
    df = behaviour_frame(n_rows=6)
    policy = BehaviourPolicy.model_validate({"baselines": {"enabled": False}})
    labels = pd.Series("running", index=df.index)
    art, findings = baselines.fit(
        df, labels, policy, groups, train_mask=pd.Series(True, index=df.index)
    )
    assert art.table.empty
    assert findings[0].finding_type == "skipped"
