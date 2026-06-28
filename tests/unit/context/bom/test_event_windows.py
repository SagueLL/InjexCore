"""Stage G — forensic candidate-date event windows."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd
from src.context.bom import aggregate, timeline
from src.context.bom.policy import ForensicWindowsPolicy

T = pd.Timestamp


def _events(
    orders: pd.DataFrame, components: pd.DataFrame, policy: ForensicWindowsPolicy
) -> pd.DataFrame:
    transitions = aggregate.classify_transitions(orders, 0.0)
    overlaps = aggregate.detect_overlaps(orders)
    gaps = aggregate.detect_gaps(orders, 0.0)
    return timeline.event_windows(
        orders, transitions, overlaps, gaps, components, policy
    )


def test_window_selects_active_orders_and_transitions(
    orders_factory: Callable[..., pd.DataFrame],
) -> None:
    orders = orders_factory(
        [
            {"order_id": "100"},
            {
                "order_id": "101",
                "start_timestamp": T("2024-09-02"),
                "end_timestamp": T("2024-09-03"),
                "recipe_version": "v2",
            },
            {
                "order_id": "999",  # far outside any window
                "start_timestamp": T("2024-10-20"),
                "end_timestamp": T("2024-10-21"),
            },
        ]
    )
    components = pd.DataFrame({"order_id": ["100"], "material_code": ["1222"]})
    policy = ForensicWindowsPolicy(candidate_dates=["2024-09-02"], window_hours=24)
    events = _events(orders, components, policy)
    assert len(events) == 1
    row = events.iloc[0]
    assert row["candidate_timestamp"] == T("2024-09-02")
    assert row["window_start"] == T("2024-09-01")
    assert row["window_end"] == T("2024-09-03")
    assert row["active_order_ids"] == "100|101"
    assert "999" not in row["active_order_ids"]
    assert "same_product_recipe_change" in row["nearby_transitions"]


def test_focus_product_and_material_flags(
    orders_factory: Callable[..., pd.DataFrame],
) -> None:
    orders = orders_factory([{"order_id": "100", "product_code": "114"}])
    components = pd.DataFrame({"order_id": ["100"], "material_code": ["1222"]})
    policy = ForensicWindowsPolicy(candidate_dates=["2024-09-01"], window_hours=24)
    events = _events(orders, components, policy)
    assert bool(events.loc[0, "focus_product_active"]) is True
    assert bool(events.loc[0, "focus_material_active"]) is True

    other = pd.DataFrame({"order_id": ["100"], "material_code": ["9999"]})
    events2 = _events(
        orders.assign(product_code="214"),
        other,
        policy.model_copy(update={"candidate_dates": ["2024-09-01"]}),
    )
    assert bool(events2.loc[0, "focus_product_active"]) is False
    assert bool(events2.loc[0, "focus_material_active"]) is False


def test_window_hours_respected(
    orders_factory: Callable[..., pd.DataFrame],
) -> None:
    orders = orders_factory(
        [
            {
                "order_id": "100",
                "start_timestamp": T("2024-09-03 12:00"),
                "end_timestamp": T("2024-09-04"),
            }
        ]
    )
    components = pd.DataFrame({"order_id": [], "material_code": []})
    narrow = ForensicWindowsPolicy(candidate_dates=["2024-09-02"], window_hours=12)
    wide = ForensicWindowsPolicy(candidate_dates=["2024-09-02"], window_hours=48)
    assert _events(orders, components, narrow).loc[0, "active_order_ids"] == ""
    assert _events(orders, components, wide).loc[0, "active_order_ids"] == "100"
