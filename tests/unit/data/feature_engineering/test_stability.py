"""Family 2 — stability features."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.data.feature_engineering import stability
from src.data.feature_engineering.policy import FeatureEngineeringPolicy


_SENSOR = "granulator_power"
_TEMP = "conditioner_inlet_temp"


def _indexed(tiny_frame_factory, n: int = 80) -> pd.DataFrame:
    df = tiny_frame_factory(n_rows=n, period_s=60.0)
    return df.set_index("timestamp")


def test_cv_finite_for_nonzero_mean(tiny_frame_factory, fe_policy, groups):
    df = _indexed(tiny_frame_factory)
    rng = np.random.default_rng(0)
    df[_SENSOR] = 50.0 + rng.normal(0, 2.0, len(df))

    findings = stability.detect(df, fe_policy, groups)
    out = stability.apply(df, findings, fe_policy, groups)

    col = f"{_SENSOR}_cv_60"
    assert col in out.columns
    last = out[col].iloc[-1]
    assert np.isfinite(last)
    assert last > 0


def test_rolling_range_is_max_minus_min(tiny_frame_factory, fe_policy, groups):
    df = _indexed(tiny_frame_factory, n=40)
    df[_SENSOR] = np.arange(len(df), dtype=float)

    findings = stability.detect(df, fe_policy, groups)
    out = stability.apply(df, findings, fe_policy, groups)

    col = f"{_SENSOR}_range_15"
    assert col in out.columns
    # window of 15 strictly-increasing samples → range = 14.
    assert out[col].iloc[20] == 14.0


def test_std_ratio_uses_upstream_columns_when_present(tiny_frame_factory, fe_policy, groups):
    df = _indexed(tiny_frame_factory, n=80)
    # Inject precomputed std columns; values are arbitrary but distinct.
    df[f"{_SENSOR}_std_5"] = 2.0
    df[f"{_SENSOR}_std_60"] = 0.5

    findings = stability.detect(df, fe_policy, groups)
    out = stability.apply(df, findings, fe_policy, groups)

    col = f"{_SENSOR}_stdratio_5_60"
    assert col in out.columns
    assert np.isclose(out[col].iloc[-1], 4.0)


def test_mad_only_emitted_for_whitelisted_units(tiny_frame_factory, fe_policy, groups):
    df = _indexed(tiny_frame_factory)
    findings = stability.detect(df, fe_policy, groups)
    mad_cols = {f.column for f in findings if f.finding_type == "mad"}
    # Temperatures (unit C) and pressures (unit bar) should be included.
    assert _TEMP in mad_cols
    # Production rate (unit kg/min) is not in the units whitelist.
    assert "granulator_production_rate" not in mad_cols


def test_disabled_returns_skipped_finding(tiny_frame_factory, groups):
    policy = FeatureEngineeringPolicy.model_validate({"stability": {"enabled": False}})
    df = _indexed(tiny_frame_factory)
    findings = stability.detect(df, policy, groups)
    assert len(findings) == 1
    assert findings[0].finding_type == "skipped"

    out = stability.apply(df, findings, policy, groups)
    assert list(out.columns) == list(df.columns)
