"""Selectors engine: hybrid regex + category + explicit overrides."""
from __future__ import annotations

import pandas as pd
import pytest

from src.data.cleaning.column_groups import ColumnGroups
from src.data.datasets.policy import SelectorSpec
from src.data.datasets.reporting import Severity
from src.data.datasets.selectors import project, select_columns


@pytest.fixture
def fixture_frame(groups: ColumnGroups) -> pd.DataFrame:
    """Frame whose columns mimic real engineered-parquet suffixes."""
    cols = [
        "timestamp",
        # Raw process sensors (from variable_classification.csv)
        "granulator_power",
        "conditioner_l2_power",
        # Time-series rolling / lag / trend
        "granulator_power_mean_60",
        "granulator_power_std_60",
        "granulator_power_lag_1",
        "granulator_power_pctchg_5",
        "granulator_power_trend_60",
        # Stability + anomaly suffixes
        "granulator_power_cv_60",
        "granulator_power_range_15",
        "granulator_power_z_60",
        "granulator_power_robust_z_60",
        # Energetic
        "granulator_power_cumkwh",
        "granulator_power_cumkwh_day",
        "granulator_power_energy_per_kg_60",
        # Operative
        "time_since_machine_off",
        "n_subsystems_running",
        # Metadata
        "work_order",
    ]
    return pd.DataFrame({c: [0.0] for c in cols})


def test_disabled_selector_emits_skipped(fixture_frame, groups):
    spec = SelectorSpec(enabled=False)
    result = select_columns(fixture_frame, spec, groups, check_name="x")
    assert result.columns == []
    assert any(f.finding_type == "skipped" for f in result.findings)


def test_pattern_match_picks_suffix_family(fixture_frame, groups):
    spec = SelectorSpec(
        enabled=True,
        include_metadata=False,
        include_patterns=[r"_cumkwh$", r"_energy_per_kg_\d+$"],
    )
    result = select_columns(fixture_frame, spec, groups, check_name="x")
    assert "granulator_power_cumkwh" in result.columns
    assert "granulator_power_energy_per_kg_60" in result.columns
    # Daily cumulative should not match the strict $ pattern.
    assert "granulator_power_cumkwh_day" not in result.columns


def test_metadata_always_kept_when_flagged(fixture_frame, groups):
    spec = SelectorSpec(enabled=True, include_metadata=True)
    result = select_columns(fixture_frame, spec, groups, check_name="x")
    assert "timestamp" in result.columns
    assert "work_order" in result.columns


def test_explicit_includes_and_unmatched_finding(fixture_frame, groups):
    spec = SelectorSpec(
        enabled=True,
        include_metadata=False,
        include_columns=["granulator_power", "does_not_exist"],
    )
    result = select_columns(fixture_frame, spec, groups, check_name="x")
    assert "granulator_power" in result.columns
    assert "does_not_exist" not in result.columns
    unmatched = [
        f for f in result.findings if f.finding_type == "unmatched_include"
    ]
    assert len(unmatched) == 1
    assert unmatched[0].severity is Severity.AWARE


def test_exclude_overrides_include(fixture_frame, groups):
    spec = SelectorSpec(
        enabled=True,
        include_metadata=False,
        include_patterns=[r"_z_60$"],
        exclude_columns=["granulator_power_z_60"],
    )
    result = select_columns(fixture_frame, spec, groups, check_name="x")
    assert "granulator_power_z_60" not in result.columns
    assert "granulator_power_robust_z_60" in result.columns


def test_category_filter_uses_groups(fixture_frame, groups):
    spec = SelectorSpec(
        enabled=True,
        include_metadata=False,
        include_categories=["process_sensor"],
    )
    result = select_columns(fixture_frame, spec, groups, check_name="x")
    # Raw process sensors are picked.
    assert "granulator_power" in result.columns
    assert "conditioner_l2_power" in result.columns
    # Engineered derivatives are NOT in the variable_classification CSV
    # so they don't get a semantic_category — category filter alone
    # must not pull them in.
    assert "granulator_power_cv_60" not in result.columns


def test_dedupe_preserves_source_order(fixture_frame, groups):
    spec = SelectorSpec(
        enabled=True,
        include_metadata=False,
        include_patterns=[r"granulator_power"],
        include_columns=["granulator_power", "granulator_power_cv_60"],
    )
    result = select_columns(fixture_frame, spec, groups, check_name="x")
    # Each column appears at most once and order matches the source.
    assert len(result.columns) == len(set(result.columns))
    source_order = list(fixture_frame.columns)
    assert result.columns == [c for c in source_order if c in result.columns]


def test_empty_projection_flags_important(fixture_frame, groups):
    spec = SelectorSpec(
        enabled=True,
        include_metadata=False,
        include_patterns=[r"^no_match_will_ever_hit$"],
    )
    result = select_columns(fixture_frame, spec, groups, check_name="x")
    assert result.columns == []
    summary = [f for f in result.findings if f.finding_type == "projection_summary"]
    assert summary and summary[0].severity is Severity.IMPORTANT


def test_project_returns_narrowed_frame(fixture_frame, groups):
    spec = SelectorSpec(
        enabled=True,
        include_metadata=False,
        include_patterns=[r"^granulator_power_cv_"],
    )
    df, _ = project(fixture_frame, spec, groups, check_name="x")
    assert list(df.columns) == ["granulator_power_cv_60"]
    assert len(df) == len(fixture_frame)
