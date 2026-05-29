"""Family 6 — statistical anomaly features."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.data.feature_engineering import anomaly_features
from src.data.feature_engineering.policy import FeatureEngineeringPolicy


_SENSOR = "granulator_power"


def _indexed(tiny_frame_factory, n: int = 200) -> pd.DataFrame:
    df = tiny_frame_factory(n_rows=n, period_s=60.0)
    return df.set_index("timestamp")


def test_rolling_z_normalised_on_stable_signal(tiny_frame_factory, fe_policy, groups):
    df = _indexed(tiny_frame_factory, n=200)
    rng = np.random.default_rng(0)
    df[_SENSOR] = 50.0 + rng.normal(0, 1.0, len(df))

    findings = anomaly_features.detect(df, fe_policy, groups)
    out = anomaly_features.apply(df, findings, fe_policy, groups)

    col = f"{_SENSOR}_z_60"
    assert col in out.columns
    z = out[col].dropna()
    # On a stable signal the rolling z-score should be approximately
    # standard-normal in the latter half of the record.
    tail = z.iloc[-100:]
    assert abs(tail.mean()) < 0.5
    assert 0.5 < tail.std() < 2.0


def test_robust_z_handles_outliers(tiny_frame_factory, fe_policy, groups):
    """A spike on a noisy baseline must register as a large robust z."""
    df = _indexed(tiny_frame_factory, n=160)
    rng = np.random.default_rng(7)
    df[_SENSOR] = 50.0 + rng.normal(0, 1.0, len(df))
    df.loc[df.index[120], _SENSOR] = 500.0  # extreme spike

    findings = anomaly_features.detect(df, fe_policy, groups)
    out = anomaly_features.apply(df, findings, fe_policy, groups)

    col = f"{_SENSOR}_robust_z_60"
    assert col in out.columns
    # With closed='left', the rolling window at index 120 sees the
    # clean baseline [60, 120). The spike value (s[120] = 500) divided
    # by a small MAD denominator produces a huge robust z at index 120.
    z_at_spike = out[col].iloc[120]
    assert np.isfinite(z_at_spike)
    assert abs(z_at_spike) > 50


def test_global_z_disabled_by_default(tiny_frame_factory, fe_policy, groups):
    df = _indexed(tiny_frame_factory, n=30)
    findings = anomaly_features.detect(df, fe_policy, groups)
    assert not any(f.finding_type == "global_z" for f in findings)


def test_global_z_emits_when_enabled(tiny_frame_factory, groups):
    policy = FeatureEngineeringPolicy.model_validate(
        {
            "anomaly_features": {
                "rolling_z": {"enabled": False},
                "robust_z": {"enabled": False},
                "global_z": {"enabled": True, "categories": ["process_sensor"]},
            }
        }
    )
    df = _indexed(tiny_frame_factory, n=20)
    df[_SENSOR] = np.arange(len(df), dtype=float)

    findings = anomaly_features.detect(df, policy, groups)
    out = anomaly_features.apply(df, findings, policy, groups)

    col = f"{_SENSOR}_z_global"
    assert col in out.columns
    z = out[col].dropna()
    assert abs(z.mean()) < 1e-9
    assert np.isclose(z.std(), 1.0, atol=0.1)


def test_disabled_returns_skipped(tiny_frame_factory, groups):
    policy = FeatureEngineeringPolicy.model_validate(
        {"anomaly_features": {"enabled": False}}
    )
    df = _indexed(tiny_frame_factory)
    findings = anomaly_features.detect(df, policy, groups)
    assert findings[0].finding_type == "skipped"

    out = anomaly_features.apply(df, findings, policy, groups)
    assert list(out.columns) == list(df.columns)
