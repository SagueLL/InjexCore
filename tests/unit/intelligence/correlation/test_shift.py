"""Validation-vs-train shift diagnostics: deltas, AWARE-only severity."""

from __future__ import annotations

import numpy as np
from src.intelligence.correlation import matrices, shift
from src.intelligence.correlation.policy import CorrelationPolicy

_POLICY = CorrelationPolicy.model_validate(
    {
        "profiles": {"min_samples_per_profile": 5},
        "thresholds": {"min_valid_observations": 5},
        "shift": {"delta_threshold": 0.5, "top_k": 10},
    }
)


def test_planted_shift_flagged_aware_only(labeled_frame, groups) -> None:
    df, labels, train_mask = labeled_frame(n_rows=60, train_fraction=0.5)
    a, b = groups.process[:2]
    n = len(df)
    base = np.linspace(0.0, 1.0, n)
    noise = np.sin(np.arange(n))
    df[a] = base
    # Train: b tracks a perfectly. Validation: b is unrelated noise.
    df[b] = np.where(train_mask.to_numpy(), base, noise)

    art, _ = matrices.fit(df, labels, _POLICY, groups, train_mask=train_mask)
    table, findings = shift.diagnose(
        df, labels, _POLICY, art.correlations, train_mask=train_mask
    )

    lo, hi = sorted([a, b])
    row = table[(table["feature_a"] == lo) & (table["feature_b"] == hi)].iloc[0]
    assert row["abs_delta"] > 0.5
    assert any(
        f.finding_type == "correlation_shift" and f.column == f"{lo}~{hi}"
        for f in findings
    )
    # Diagnostics only: nothing above AWARE severity.
    assert all(f.severity.value in ("aware", "normal") for f in findings)


def test_stable_relationship_not_flagged(labeled_frame, groups) -> None:
    df, labels, train_mask = labeled_frame(n_rows=60, train_fraction=0.5)
    a, b = groups.process[:2]
    base = np.linspace(0.0, 1.0, len(df))
    df[a] = base
    df[b] = 2.0 * base  # identical relationship in both windows

    art, _ = matrices.fit(df, labels, _POLICY, groups, train_mask=train_mask)
    table, findings = shift.diagnose(
        df, labels, _POLICY, art.correlations, train_mask=train_mask
    )
    lo, hi = sorted([a, b])
    row = table[(table["feature_a"] == lo) & (table["feature_b"] == hi)].iloc[0]
    assert row["abs_delta"] < 0.05
    assert not any(
        f.finding_type == "correlation_shift" and f.column == f"{lo}~{hi}"
        for f in findings
    )


def test_disabled_shift_returns_empty(labeled_frame, groups) -> None:
    df, labels, train_mask = labeled_frame(n_rows=20, train_fraction=0.5)
    policy = CorrelationPolicy.model_validate(
        {
            "profiles": {"min_samples_per_profile": 5},
            "thresholds": {"min_valid_observations": 5},
            "shift": {"enabled": False},
        }
    )
    art, _ = matrices.fit(df, labels, policy, groups, train_mask=train_mask)
    table, findings = shift.diagnose(
        df, labels, policy, art.correlations, train_mask=train_mask
    )
    assert table.empty
    assert findings == []
