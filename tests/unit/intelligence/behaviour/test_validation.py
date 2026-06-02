"""Behaviour Intelligence — profile-quality diagnostics."""

from __future__ import annotations

import pandas as pd
from src.intelligence.behaviour import validation
from src.intelligence.behaviour.policy import BehaviourPolicy

_POLICY = BehaviourPolicy.model_validate({})


def _labels(values: list[str]) -> pd.Series:
    idx = pd.date_range("2025-01-01", periods=len(values), freq="60s")
    return pd.Series(values, index=idx)


def test_distribution_counts() -> None:
    labels = _labels(
        [
            "stopped",
            "stopped",
            "high_production",
            "high_production",
            "high_production",
            "stopped",
        ]
    )
    art, _ = validation.build(
        labels, _POLICY, train_mask=pd.Series(True, index=labels.index)
    )
    dist = art.distribution.set_index("profile")["n_rows"].to_dict()
    assert dist["stopped"] == 3
    assert dist["high_production"] == 3


def test_durations_segments() -> None:
    labels = _labels(
        [
            "stopped",
            "stopped",
            "high_production",
            "high_production",
            "high_production",
            "stopped",
        ]
    )
    art, _ = validation.build(
        labels, _POLICY, train_mask=pd.Series(True, index=labels.index)
    )
    dur = art.durations.set_index("profile")
    # stopped: a 2-row segment + a 1-row segment.
    assert dur.loc["stopped", "n_segments"] == 2
    assert dur.loc["stopped", "max_len"] == 2
    # high_production: a single 3-row segment.
    assert dur.loc["high_production", "n_segments"] == 1
    assert dur.loc["high_production", "max_len"] == 3


def test_transitions_counted() -> None:
    labels = _labels(
        [
            "stopped",
            "stopped",
            "high_production",
            "high_production",
            "high_production",
            "stopped",
        ]
    )
    art, _ = validation.build(
        labels, _POLICY, train_mask=pd.Series(True, index=labels.index)
    )
    pairs = {
        (r.from_profile, r.to_profile): r.count for r in art.transitions.itertuples()
    }
    assert pairs[("stopped", "high_production")] == 1
    assert pairs[("high_production", "stopped")] == 1


def test_coverage_and_unsupported() -> None:
    labels = _labels(["stopped", "high_production", "unknown", "high_production"])
    train_mask = pd.Series([True, True, False, False], index=labels.index)
    art, findings = validation.build(labels, _POLICY, train_mask=train_mask)
    assert art.coverage["n_total"] == 4
    assert art.coverage["n_train"] == 2
    assert art.coverage["n_unknown"] == 1
    assert art.coverage["labeled_pct"] == 0.75
    assert "cleaning" in art.unsupported
    assert any(f.finding_type == "unlabeled_rows" for f in findings)
