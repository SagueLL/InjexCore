"""Context transitions: multi-typed rows + BOM overlap/gap edges."""

from __future__ import annotations

import pandas as pd
from src.context.operational.policy import TransitionsPolicy
from src.context.operational.transitions import detect_transitions


def _overlay(rows: list[dict]) -> pd.DataFrame:
    base = {
        "profile": "mid_production",
        "steam_context": "steam_conditioning_off",
        "sensor_health_context": "all_sensors_healthy",
        "product_code": "114",
        "recipe_context_key": "114:v1:sig",
        "is_transition_overlap": False,
        "bom_context_status": "matched_single_order",
    }
    frame = pd.DataFrame([{**base, **r} for r in rows])
    frame.insert(
        0,
        "timestamp",
        pd.date_range("2024-09-01", periods=len(frame), freq="1min"),
    )
    return frame


def test_no_transitions_on_constant_context() -> None:
    overlay = _overlay([{} for _ in range(10)])
    assert detect_transitions(overlay, TransitionsPolicy()).empty


def test_simultaneous_changes_preserved_multi_typed() -> None:
    overlay = _overlay(
        [
            {},
            {},
            {
                "profile": "stopped",
                "steam_context": "steam_conditioning_on",
                "product_code": "214",
                "recipe_context_key": "214:v2:sig2",
            },
        ]
    )
    events = detect_transitions(overlay, TransitionsPolicy())
    assert len(events) == 1
    row = events.iloc[0]
    assert row["transition_types"] == (
        "product_change|profile_change|recipe_change|steam_context_change"
    )
    assert row["previous_profile"] == "mid_production"
    assert row["new_profile"] == "stopped"
    assert row["previous_product_code"] == "114"
    assert row["new_product_code"] == "214"


def test_bom_overlap_and_gap_edges() -> None:
    overlay = _overlay(
        [
            {},
            {"is_transition_overlap": True, "bom_context_status": "transition_overlap"},
            {"is_transition_overlap": True, "bom_context_status": "transition_overlap"},
            {},
            {"bom_context_status": "no_active_order"},
            {"bom_context_status": "no_active_order"},
            {},
        ]
    )
    events = detect_transitions(overlay, TransitionsPolicy())
    by_ts = events.set_index(events["transition_timestamp"].dt.minute)
    assert "bom_overlap_start" in by_ts.loc[1, "transition_types"]
    assert "bom_overlap_end" in by_ts.loc[3, "transition_types"]
    assert "bom_gap_start" in by_ts.loc[4, "transition_types"]
    assert "bom_gap_end" in by_ts.loc[6, "transition_types"]


def test_sensor_health_change_tracked() -> None:
    overlay = _overlay([{}, {"sensor_health_context": "sensor_faulty"}, {}])
    events = detect_transitions(overlay, TransitionsPolicy())
    assert len(events) == 2
    assert (events["transition_types"] == "sensor_health_change").all()


def test_tracking_toggles_respected() -> None:
    overlay = _overlay([{}, {"profile": "stopped"}])
    policy = TransitionsPolicy(track_profile=False)
    assert detect_transitions(overlay, policy).empty
