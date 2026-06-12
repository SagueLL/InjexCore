"""Gate A blockers, summaries and report rendering."""

from __future__ import annotations

import pandas as pd
import pytest
from src.context.operational import validation
from src.context.operational.reporting import (
    coverage_summary,
    daily_share,
    dimension_summary,
    first_sustained_day,
    transitions_near,
)


def test_validate_upstream_passes_and_records(
    master_ts_factory, health_timeline_factory, bom_timeline_factory
) -> None:
    master_ts = master_ts_factory(600)
    compat = validation.validate_upstream(
        master_ts,
        600,
        health_timeline_factory(600),
        bom_timeline_factory(600),
        {"fit_window": {"train_end": "2024-09-01 05:00:00"}},
        {"train_window": {"train_end": "2024-09-01 05:00:00"}},
    )
    assert compat["master_rows"] == 600
    assert compat["train_end_coherent"] is True


def test_validate_upstream_blocks_row_mismatch(
    master_ts_factory, health_timeline_factory, bom_timeline_factory
) -> None:
    with pytest.raises(validation.OperationalContextBlockerError, match="rows"):
        validation.validate_upstream(
            master_ts_factory(600),
            600,
            health_timeline_factory(599),
            bom_timeline_factory(600),
            {},
            {},
        )


def test_validate_upstream_blocks_expected_rows(
    master_ts_factory, health_timeline_factory, bom_timeline_factory
) -> None:
    with pytest.raises(validation.OperationalContextBlockerError, match="expected"):
        validation.validate_upstream(
            master_ts_factory(600),
            700,
            health_timeline_factory(600),
            bom_timeline_factory(600),
            {},
            {},
        )


def test_validate_upstream_blocks_train_end_mismatch(
    master_ts_factory, health_timeline_factory, bom_timeline_factory
) -> None:
    with pytest.raises(validation.OperationalContextBlockerError, match="incompatible"):
        validation.validate_upstream(
            master_ts_factory(600),
            600,
            health_timeline_factory(600),
            bom_timeline_factory(600),
            {"fit_window": {"train_end": "2024-09-01 05:00:00"}},
            {"train_window": {"train_end": "2024-09-02 05:00:00"}},
        )


def _tiny_overlay() -> pd.DataFrame:
    ts = pd.date_range("2024-09-01", periods=8, freq="1D")
    return pd.DataFrame(
        {
            "timestamp": ts,
            "is_train": [True] * 4 + [False] * 4,
            "profile": ["stopped"] * 8,
            "steam_context": ["steam_conditioning_off"] * 4
            + ["steam_conditioning_on"] * 4,
            "sensor_health_context": ["all_sensors_healthy"] * 8,
            "bom_context_status": ["matched_single_order"] * 8,
        }
    )


def test_dimension_and_coverage_summaries() -> None:
    overlay = _tiny_overlay()
    steam = dimension_summary(overlay, "steam_context")
    by_value = steam.set_index("value")
    assert by_value.loc["steam_conditioning_on", "row_count"] == 4
    assert by_value.loc["steam_conditioning_off", "n_train_rows"] == 4
    coverage = coverage_summary(overlay)
    assert set(coverage["dimension"]) == {
        "profile",
        "steam_context",
        "sensor_health_context",
        "bom_context_status",
    }


def test_daily_share_and_first_sustained_day() -> None:
    overlay = _tiny_overlay()
    daily = daily_share(overlay, "steam_context")
    first = first_sustained_day(daily, "steam_conditioning_on")
    assert first == pd.Timestamp("2024-09-05")  # 4 consecutive full-on days
    assert first_sustained_day(daily, "not_a_context") is None


def test_transitions_near_window() -> None:
    transitions = pd.DataFrame(
        {
            "transition_timestamp": [
                pd.Timestamp("2024-09-15 23:00"),
                pd.Timestamp("2024-09-16 12:00"),
                pd.Timestamp("2024-09-20 00:00"),
            ],
            "transition_types": ["steam_context_change"] * 3,
        }
    )
    near = transitions_near(transitions, "2024-09-16", 24)
    assert len(near) == 2
