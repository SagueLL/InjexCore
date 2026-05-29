"""Anomaly / forecasting / energy projection modules.

These tests build a master-like fixture with column names that mimic
the real engineered-parquet output (the suffix conventions emitted by
the time-series and feature-engineering stages), apply the real policy
from ``configs/specialized_datasets.yaml`` and assert the projection
picks the right family of columns.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.data.cleaning.column_groups import ColumnGroups
from src.data.datasets import (
    anomaly_projection,
    energy_projection,
    forecasting_projection,
)
from src.data.datasets.policy import SpecializedDatasetsPolicy


@pytest.fixture
def master_like(groups: ColumnGroups) -> pd.DataFrame:
    """Tiny DataFrame whose columns mimic the real engineered parquet."""
    cols = [
        "timestamp",
        "work_order",
        # Raw process sensors (Process category)
        "granulator_power",
        "conditioner_l2_power",
        "expander_ex2_power",
        "extruder_specific_energy",
        "granulator_production_rate",
        "granulator_roller_gap",
        "steam_valve_flow_me2",
        "steam_valve_pressure_me2",
        "conditioner_steam_loop_temp",
        "conditioner_inlet_temp",
        "expander_ex2_outlet_temp",
        "inlet_hopper_humidity",
        "inlet_hopper_temp",
        # Control / state percent registers
        "granulator_g2_state_pct",
        "conditioner_l2_state_pct",
        "feeder_al2_state_pct",
        # Time-series rolling + lag + trend suffixes
        "granulator_power_mean_60",
        "granulator_power_std_60",
        "granulator_power_lag_1",
        "granulator_power_pctchg_5",
        "granulator_power_velocity_1",
        "granulator_power_trend_60",
        "granulator_g2_running_runfrac_60",
        # Stability + anomaly suffixes
        "granulator_power_cv_60",
        "granulator_power_range_15",
        "granulator_power_mad_60",
        "granulator_power_stdratio_5_60",
        "granulator_power_z_60",
        "granulator_power_robust_z_60",
        "granulator_power_accel_1",
        "granulator_power_signchanges_15",
        "granulator_g2_running_tsla",
        "granulator_g2_alarm_edges_60",
        # SP-PV deviations
        "granulator_power_minus_granulator_power_sp",
        # Energetic features
        "granulator_power_cumkwh",
        "granulator_power_cumkwh_day",
        "granulator_power_energy_per_kg_60",
        # Physical ratios
        "granulator_kwh_per_kg",
        "extruder_kwh_per_kg",
        "production_per_steam",
        "power_balance_extruder_vs_conditioner",
        "pressure_ratio_expander_steam",
        # Operative features
        "time_since_machine_off",
        "n_subsystems_running",
        "cumulative_starts",
        "time_since_any_alarm",
        "any_alarm_while_running",
    ]
    return pd.DataFrame({c: [0.0] for c in cols})


def test_anomaly_projection_picks_local_deviation_features(
    master_like, datasets_policy: SpecializedDatasetsPolicy, groups,
):
    df, _ = anomaly_projection.run(master_like, datasets_policy, groups)
    selected = set(df.columns)
    # Stability + statistical-anomaly + derivatives + state-evolution
    for col in (
        "granulator_power_cv_60",
        "granulator_power_range_15",
        "granulator_power_mad_60",
        "granulator_power_stdratio_5_60",
        "granulator_power_z_60",
        "granulator_power_robust_z_60",
        "granulator_power_accel_1",
        "granulator_power_signchanges_15",
        "granulator_g2_running_tsla",
        "granulator_g2_alarm_edges_60",
        "time_since_machine_off",
        "n_subsystems_running",
        "cumulative_starts",
        "any_alarm_while_running",
    ):
        assert col in selected, col
    # Forecasting-only suffixes should NOT leak in.
    for col in ("granulator_power_lag_1", "granulator_power_mean_60"):
        assert col not in selected, col
    # Metadata preserved.
    assert "timestamp" in selected


def test_forecasting_projection_picks_predictive_structure(
    master_like, datasets_policy: SpecializedDatasetsPolicy, groups,
):
    df, _ = forecasting_projection.run(master_like, datasets_policy, groups)
    selected = set(df.columns)
    # Lags, pctchg, velocity, rolling agg, trend, runfrac, SP-PV
    for col in (
        "granulator_power_lag_1",
        "granulator_power_pctchg_5",
        "granulator_power_velocity_1",
        "granulator_power_mean_60",
        "granulator_power_std_60",
        "granulator_power_trend_60",
        "granulator_g2_running_runfrac_60",
        "granulator_power_minus_granulator_power_sp",
    ):
        assert col in selected, col
    # Raw process-sensor targets kept by category filter.
    assert "granulator_power" in selected
    # Stability-only suffix should not pull in CV.
    assert "granulator_power_cv_60" not in selected


def test_energy_projection_picks_energy_and_load_context(
    master_like, datasets_policy: SpecializedDatasetsPolicy, groups,
):
    df, _ = energy_projection.run(master_like, datasets_policy, groups)
    selected = set(df.columns)
    # Raw energy / production / load context
    for col in (
        "granulator_power",
        "conditioner_l2_power",
        "expander_ex2_power",
        "extruder_specific_energy",
        "granulator_production_rate",
        "granulator_g2_state_pct",
        "conditioner_l2_state_pct",
        "feeder_al2_state_pct",
        "granulator_roller_gap",
        "steam_valve_flow_me2",
        "steam_valve_pressure_me2",
    ):
        assert col in selected, col
    # Engineered energetic features.
    for col in (
        "granulator_power_cumkwh",
        "granulator_power_cumkwh_day",
        "granulator_power_energy_per_kg_60",
        "granulator_kwh_per_kg",
        "extruder_kwh_per_kg",
        "production_per_steam",
        "power_balance_extruder_vs_conditioner",
        "pressure_ratio_expander_steam",
    ):
        assert col in selected, col
    # Operational load context from runtime fraction.
    assert "granulator_g2_running_runfrac_60" in selected
    # Statistical-anomaly suffixes are not part of the energy projection.
    assert "granulator_power_z_60" not in selected
