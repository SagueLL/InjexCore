"""Overlay assembly, BOM preservation, context_key, hard invariants."""

from __future__ import annotations

import pandas as pd
import pytest
from src.context.operational.overlay import OVERLAY_COLUMNS, build_overlay, context_key
from src.context.operational.policy import ContextKeyPolicy, SteamPolicy
from src.context.operational.steam import (
    classify_steam_context,
    steam_activity_indicator,
)
from src.context.operational.validation import (
    OperationalContextBlockerError,
    validate_overlay,
)


def _build(
    master_ts_factory,
    profiles_factory,
    steam_frame_factory,
    health_timeline_factory,
    bom_timeline_factory,
    periods: int = 600,
) -> tuple[pd.DataFrame, pd.Series]:
    master_ts = master_ts_factory(periods)
    profiles = profiles_factory(periods)
    steam_df = steam_frame_factory(periods)
    policy = SteamPolicy(window_rows=31, min_valid_rows=10)
    steam_ctx = classify_steam_context(
        steam_activity_indicator(steam_df, policy), steam_df, policy
    )
    health = health_timeline_factory(periods, faulty=(450, 600))
    bom = bom_timeline_factory(periods)
    is_train = pd.Series([True] * (periods // 2) + [False] * (periods - periods // 2))
    overlay = build_overlay(
        master_ts, profiles, is_train, steam_ctx, health, bom, ContextKeyPolicy()
    )
    return overlay, master_ts


def test_overlay_schema_and_alignment(
    master_ts_factory,
    profiles_factory,
    steam_frame_factory,
    health_timeline_factory,
    bom_timeline_factory,
) -> None:
    overlay, master_ts = _build(
        master_ts_factory,
        profiles_factory,
        steam_frame_factory,
        health_timeline_factory,
        bom_timeline_factory,
    )
    assert list(overlay.columns) == OVERLAY_COLUMNS
    validate_overlay(overlay, master_ts)  # passes all hard invariants
    assert len(overlay) == 600


def test_bom_columns_preserved_overlaps_unresolved(
    master_ts_factory,
    profiles_factory,
    steam_frame_factory,
    health_timeline_factory,
    bom_timeline_factory,
) -> None:
    overlay, _ = _build(
        master_ts_factory,
        profiles_factory,
        steam_frame_factory,
        health_timeline_factory,
        bom_timeline_factory,
    )
    overlap_rows = overlay[overlay["bom_context_status"] == "transition_overlap"]
    assert len(overlap_rows) == 30
    assert overlap_rows["order_id"].isna().all()  # never silently pick one
    assert (overlap_rows["order_ids"] == "100|101").all()
    gap_rows = overlay[overlay["bom_context_status"] == "no_active_order"]
    assert (~gap_rows["has_active_order"].astype(bool)).all()


def test_context_key_is_deterministic_and_null_stable() -> None:
    frame = pd.DataFrame(
        {
            "profile": ["stopped", "run"],
            "steam_context": ["steam_conditioning_off", None],
            "sensor_health_context": ["all_sensors_healthy", ""],
            "bom_context_status": ["matched_single_order", "no_active_order"],
        }
    )
    key = context_key(
        frame,
        ["profile", "steam_context", "sensor_health_context", "bom_context_status"],
    )
    assert key.iloc[0] == (
        "stopped:steam_conditioning_off:all_sensors_healthy:matched_single_order"
    )
    assert key.iloc[1] == "run:null:null:no_active_order"


def test_validate_overlay_rejects_scalar_on_overlap(
    master_ts_factory,
    profiles_factory,
    steam_frame_factory,
    health_timeline_factory,
    bom_timeline_factory,
) -> None:
    overlay, master_ts = _build(
        master_ts_factory,
        profiles_factory,
        steam_frame_factory,
        health_timeline_factory,
        bom_timeline_factory,
    )
    bad = overlay.copy()
    bad.loc[bad["bom_context_status"] == "transition_overlap", "order_id"] = "100"
    with pytest.raises(OperationalContextBlockerError, match="no-silent-selection"):
        validate_overlay(bad, master_ts)


def test_validate_overlay_rejects_timestamp_mismatch(
    master_ts_factory,
    profiles_factory,
    steam_frame_factory,
    health_timeline_factory,
    bom_timeline_factory,
) -> None:
    overlay, master_ts = _build(
        master_ts_factory,
        profiles_factory,
        steam_frame_factory,
        health_timeline_factory,
        bom_timeline_factory,
    )
    with pytest.raises(OperationalContextBlockerError, match="rows"):
        validate_overlay(overlay.iloc[:-1], master_ts)
