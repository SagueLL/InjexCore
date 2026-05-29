"""Family 3 — physical ratios."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.data.feature_engineering import physical_ratios
from src.data.feature_engineering.policy import FeatureEngineeringPolicy


def _indexed(tiny_frame_factory, n: int = 20) -> pd.DataFrame:
    df = tiny_frame_factory(n_rows=n, period_s=60.0)
    return df.set_index("timestamp")


def test_ratio_math(tiny_frame_factory, fe_policy, groups):
    df = _indexed(tiny_frame_factory)
    df["granulator_power"] = 40.0
    df["granulator_production_rate"] = 8.0  # kg/min

    findings = physical_ratios.detect(df, fe_policy, groups)
    out = physical_ratios.apply(df, findings, fe_policy, groups)

    col = "granulator_kwh_per_kg"
    assert col in out.columns
    assert np.allclose(out[col], 5.0)


def test_diff_op(tiny_frame_factory, fe_policy, groups):
    df = _indexed(tiny_frame_factory)
    df["conditioner_steam_loop_temp"] = 80.0
    df["conditioner_inlet_temp"] = 55.0

    findings = physical_ratios.detect(df, fe_policy, groups)
    out = physical_ratios.apply(df, findings, fe_policy, groups)

    assert "temp_rise_conditioner" in out.columns
    assert np.allclose(out["temp_rise_conditioner"], 25.0)


def test_scale_op(tiny_frame_factory, fe_policy, groups):
    df = _indexed(tiny_frame_factory)
    df["extruder_specific_energy"] = 200.0  # kWh/t

    findings = physical_ratios.detect(df, fe_policy, groups)
    out = physical_ratios.apply(df, findings, fe_policy, groups)

    assert "extruder_kwh_per_kg" in out.columns
    assert np.allclose(out["extruder_kwh_per_kg"], 0.2)


def test_division_by_zero_becomes_nan(tiny_frame_factory, fe_policy, groups):
    df = _indexed(tiny_frame_factory)
    df["granulator_power"] = 40.0
    df["granulator_production_rate"] = 0.0

    findings = physical_ratios.detect(df, fe_policy, groups)
    out = physical_ratios.apply(df, findings, fe_policy, groups)

    assert out["granulator_kwh_per_kg"].isna().all()


def test_missing_input_yields_important_finding(tiny_frame_factory, fe_policy, groups):
    df = _indexed(tiny_frame_factory).drop(columns=["granulator_production_rate"])
    findings = physical_ratios.detect(df, fe_policy, groups)
    important = [
        f for f in findings
        if f.finding_type == "ratio_missing_input"
        and f.severity.value == "important"
    ]
    assert important


def test_high_nan_rate_surfaces_aware_finding(tiny_frame_factory, groups):
    """When more than nan_rate_warn of a ratio's output is NaN, emit AWARE."""
    policy = FeatureEngineeringPolicy.model_validate(
        {
            "physical_ratios": {
                "enabled": True,
                "epsilon": 1.0e-6,
                "nan_rate_warn": 0.10,
                "ratios": [
                    {
                        "name": "granulator_kwh_per_kg",
                        "op": "ratio",
                        "a": "granulator_power",
                        "b": "granulator_production_rate",
                    },
                ],
            }
        }
    )
    df = _indexed(tiny_frame_factory, n=20)
    df["granulator_power"] = 40.0
    df["granulator_production_rate"] = 0.0  # 100% NaN output

    findings = physical_ratios.detect(df, policy, groups)
    physical_ratios.apply(df, findings, policy, groups)

    assert any(
        f.finding_type == "ratio_high_nan_rate"
        and f.severity.value == "aware"
        for f in findings
    )


def test_disabled_returns_skipped(tiny_frame_factory, groups):
    policy = FeatureEngineeringPolicy.model_validate(
        {"physical_ratios": {"enabled": False}}
    )
    df = _indexed(tiny_frame_factory)
    findings = physical_ratios.detect(df, policy, groups)
    assert findings[0].finding_type == "skipped"

    out = physical_ratios.apply(df, findings, policy, groups)
    assert list(out.columns) == list(df.columns)
