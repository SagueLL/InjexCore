"""Family 4 — energetic features."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.data.feature_engineering import energetic_features
from src.data.feature_engineering.policy import FeatureEngineeringPolicy


def _indexed(tiny_frame_factory, n: int = 80) -> pd.DataFrame:
    df = tiny_frame_factory(n_rows=n, period_s=60.0)
    return df.set_index("timestamp")


def test_cumulative_energy_is_monotonic(tiny_frame_factory, fe_policy, groups):
    df = _indexed(tiny_frame_factory)
    df["granulator_power"] = 60.0  # constant load

    findings = energetic_features.detect(df, fe_policy, groups)
    out = energetic_features.apply(df, findings, fe_policy, groups)

    col = "granulator_power_cumkwh"
    assert col in out.columns
    # Each sample adds 60 * (60/3600) = 1.0
    assert np.isclose(out[col].iloc[0], 1.0)
    assert np.isclose(out[col].iloc[1] - out[col].iloc[0], 1.0)
    assert (out[col].diff().dropna() >= 0).all()


def test_cumulative_energy_daily_resets(tiny_frame_factory, fe_policy, groups):
    df = tiny_frame_factory(n_rows=4, period_s=60.0)
    # Make samples cross midnight: 23:59:00, 23:59:60? no — use daily steps.
    df["timestamp"] = pd.to_datetime(
        [
            "2025-01-01 23:59:00",
            "2025-01-02 00:00:00",
            "2025-01-02 00:01:00",
            "2025-01-02 00:02:00",
        ]
    )
    df = df.set_index("timestamp")
    df["granulator_power"] = 60.0

    findings = energetic_features.detect(df, fe_policy, groups)
    out = energetic_features.apply(df, findings, fe_policy, groups)

    col = "granulator_power_cumkwh_day"
    assert col in out.columns
    # First sample on 2025-01-01 → 1.0
    assert np.isclose(out[col].iloc[0], 1.0)
    # First sample on 2025-01-02 should reset to 1.0, not continue from 2.0
    assert np.isclose(out[col].iloc[1], 1.0)
    assert np.isclose(out[col].iloc[2], 2.0)


def test_energy_per_kg_window(tiny_frame_factory, fe_policy, groups):
    df = _indexed(tiny_frame_factory, n=80)
    df["granulator_power"] = 60.0          # constant power %
    df["granulator_production_rate"] = 10.0  # kg/min

    findings = energetic_features.detect(df, fe_policy, groups)
    out = energetic_features.apply(df, findings, fe_policy, groups)

    col = "granulator_power_energy_per_kg_60"
    assert col in out.columns
    # power_sum = 60 samples * 60 * dt_h = 60 kWh-equivalents at the
    # back-of-window. prod_sum = 60 samples * 10 kg/min * 1 min = 600 kg.
    # Ratio = 60 / 600 = 0.1.
    last = out[col].iloc[-1]
    assert np.isfinite(last)
    assert np.isclose(last, 0.1, atol=1e-6)


def test_missing_production_column_warns(tiny_frame_factory, fe_policy, groups):
    df = _indexed(tiny_frame_factory).drop(columns=["granulator_production_rate"])
    findings = energetic_features.detect(df, fe_policy, groups)
    assert any(
        f.finding_type == "energy_per_kg_missing_input"
        and f.severity.value == "important"
        for f in findings
    )


def test_disabled_returns_skipped(tiny_frame_factory, groups):
    policy = FeatureEngineeringPolicy.model_validate(
        {"energetic_features": {"enabled": False}}
    )
    df = _indexed(tiny_frame_factory)
    findings = energetic_features.detect(df, policy, groups)
    assert findings[0].finding_type == "skipped"

    out = energetic_features.apply(df, findings, policy, groups)
    assert list(out.columns) == list(df.columns)
