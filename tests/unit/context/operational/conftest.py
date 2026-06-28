"""Fixtures for the Operational Context Overlay unit tests."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd
import pytest
from src.config import PROJECT_ROOT
from src.context.operational.bom import BOM_COLUMNS
from src.context.operational.policy import OperationalContextPolicy, load_policy
from src.context.operational.sensor_health import HEALTH_COLUMNS


@pytest.fixture(scope="session")
def op_policy() -> OperationalContextPolicy:
    """Real policy loaded from configs/operational_context.yaml."""
    return load_policy(PROJECT_ROOT / "configs" / "operational_context.yaml")


@pytest.fixture
def master_ts_factory() -> Callable[..., pd.Series]:
    def _make(periods: int = 600, start: str = "2024-09-01") -> pd.Series:
        return pd.Series(
            pd.date_range(start, periods=periods, freq="1min"), name="timestamp"
        )

    return _make


@pytest.fixture
def health_timeline_factory(
    master_ts_factory: Callable[..., pd.Series],
) -> Callable[..., pd.DataFrame]:
    """Quality timeline with an optional faulty window."""

    def _make(
        periods: int = 600, faulty: tuple[int, int] | None = None
    ) -> pd.DataFrame:
        ts = master_ts_factory(periods)
        frame = pd.DataFrame({"timestamp": ts})
        frame["sensor_health_context"] = "all_sensors_healthy"
        for col in HEALTH_COLUMNS[1:]:
            frame[col] = ""
        if faulty is not None:
            i, j = faulty
            frame.loc[i : j - 1, "sensor_health_context"] = "sensor_faulty"
            frame.loc[i : j - 1, "faulty_sensors"] = "s1"
            frame.loc[i : j - 1, "quarantine_recommended_sensors"] = "s1"
        frame["n_sensors_evaluated"] = 3
        return frame

    return _make


@pytest.fixture
def bom_timeline_factory(
    master_ts_factory: Callable[..., pd.Series],
) -> Callable[..., pd.DataFrame]:
    """BOM timeline with matched / gap / overlap stretches."""

    def _make(
        periods: int = 600,
        gap: tuple[int, int] = (200, 260),
        overlap: tuple[int, int] = (400, 430),
    ) -> pd.DataFrame:
        ts = master_ts_factory(periods)
        frame = pd.DataFrame({"timestamp": ts})
        for col in BOM_COLUMNS:
            frame[col] = None
        frame["bom_context_status"] = "matched_single_order"
        frame["active_order_count"] = 1
        frame["order_id"] = "100"
        frame["order_ids"] = "100"
        frame["product_code"] = "114"
        frame["product_codes"] = "114"
        frame["recipe_version"] = "v1"
        frame["recipe_versions"] = "v1"
        frame["recipe_context_key"] = "114:v1:sig"
        frame["recipe_context_keys"] = "114:v1:sig"
        frame["bom_signature"] = "sig"
        frame["bom_signatures"] = "sig"
        frame["is_transition_overlap"] = False
        frame["has_active_order"] = True
        gi, gj = gap
        frame.loc[gi : gj - 1, "bom_context_status"] = "no_active_order"
        frame.loc[gi : gj - 1, "active_order_count"] = 0
        frame.loc[gi : gj - 1, "has_active_order"] = False
        for col in (
            "order_id",
            "order_ids",
            "product_code",
            "product_codes",
            "recipe_version",
            "recipe_versions",
            "recipe_context_key",
            "recipe_context_keys",
            "bom_signature",
            "bom_signatures",
        ):
            frame.loc[gi : gj - 1, col] = (
                None
                if col.endswith(("_id", "code", "version", "key", "signature"))
                else ""
            )
        oi, oj = overlap
        frame.loc[oi : oj - 1, "bom_context_status"] = "transition_overlap"
        frame.loc[oi : oj - 1, "active_order_count"] = 2
        frame.loc[oi : oj - 1, "is_transition_overlap"] = True
        for scalar in (
            "order_id",
            "product_code",
            "recipe_version",
            "recipe_context_key",
            "bom_signature",
        ):
            frame.loc[oi : oj - 1, scalar] = None
        frame.loc[oi : oj - 1, "order_ids"] = "100|101"
        return frame

    return _make


@pytest.fixture
def steam_frame_factory(
    master_ts_factory: Callable[..., pd.Series],
) -> Callable[..., pd.DataFrame]:
    """Master steam columns: off → toggling → on thirds."""

    def _make(periods: int = 600) -> pd.DataFrame:
        ts = master_ts_factory(periods)
        third = periods // 3
        rng = np.random.default_rng(5)
        pressure = np.r_[
            rng.normal(0.2, 0.05, third),
            np.where(np.arange(third) // 30 % 2 == 0, 2.6, 0.2),
            rng.normal(2.6, 0.1, periods - 2 * third),
        ]
        temp = np.r_[
            rng.normal(34, 1, third),
            np.where(np.arange(third) // 30 % 2 == 0, 86.0, 34.0),
            rng.normal(86, 1, periods - 2 * third),
        ]
        return pd.DataFrame(
            {
                "steam_valve_pressure_me2": pressure,
                "conditioner_steam_loop_temp": temp,
            },
            index=pd.DatetimeIndex(ts, name="timestamp"),
        )

    return _make


@pytest.fixture
def profiles_factory() -> Callable[..., pd.Series]:
    def _make(periods: int = 600) -> pd.Series:
        idx = pd.date_range("2024-09-01", periods=periods, freq="1min")
        values = ["stopped"] * (periods // 3) + ["mid_production"] * (
            periods - periods // 3
        )
        return pd.Series(values, index=idx, name="profile")

    return _make
