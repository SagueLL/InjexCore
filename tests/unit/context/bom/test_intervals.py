"""Stage D — overlap/gap detection and transition classification."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd
from src.context.bom import aggregate

T = pd.Timestamp


def test_touching_orders_no_overlap_no_gap(
    orders_factory: Callable[..., pd.DataFrame],
) -> None:
    orders = orders_factory(
        [
            {"order_id": "100", "end_timestamp": T("2024-09-02")},
            {
                "order_id": "101",
                "start_timestamp": T("2024-09-02"),
                "end_timestamp": T("2024-09-03"),
            },
        ]
    )
    assert aggregate.detect_overlaps(orders).empty  # half-open windows
    assert aggregate.detect_gaps(orders, 0.0).empty


def test_overlap_window_bounds_and_membership(
    orders_factory: Callable[..., pd.DataFrame],
) -> None:
    orders = orders_factory(
        [
            {"order_id": "100"},
            {
                "order_id": "101",
                "start_timestamp": T("2024-09-01 12:00"),
                "end_timestamp": T("2024-09-03"),
                "product_code": "214",
            },
        ]
    )
    overlaps = aggregate.detect_overlaps(orders)
    assert len(overlaps) == 1
    row = overlaps.iloc[0]
    assert row["overlap_start"] == T("2024-09-01 12:00")
    assert row["overlap_end"] == T("2024-09-02")
    assert row["duration_seconds"] == 12 * 3600
    assert row["active_order_ids"] == "100|101"
    assert row["active_product_codes"] == "114|214"
    assert row["overlap_count"] == 2


def test_gap_with_previous_and_next_order(
    orders_factory: Callable[..., pd.DataFrame],
) -> None:
    orders = orders_factory(
        [
            {"order_id": "100"},
            {
                "order_id": "101",
                "start_timestamp": T("2024-09-04"),
                "end_timestamp": T("2024-09-05"),
            },
        ]
    )
    gaps = aggregate.detect_gaps(orders, 0.0)
    assert len(gaps) == 1
    row = gaps.iloc[0]
    assert row["gap_start"] == T("2024-09-02")
    assert row["gap_end"] == T("2024-09-04")
    assert row["duration_seconds"] == 2 * 86400
    assert row["previous_order_id"] == "100"
    assert row["next_order_id"] == "101"


def test_gap_within_tolerance_ignored(
    orders_factory: Callable[..., pd.DataFrame],
) -> None:
    orders = orders_factory(
        [
            {"order_id": "100"},
            {
                "order_id": "101",
                "start_timestamp": T("2024-09-02 00:00:30"),
                "end_timestamp": T("2024-09-03"),
            },
        ]
    )
    assert aggregate.detect_gaps(orders, 60.0).empty
    assert len(aggregate.detect_gaps(orders, 0.0)) == 1


def _pair(orders_factory: Callable[..., pd.DataFrame], second: dict) -> pd.DataFrame:
    base_second = {
        "order_id": "101",
        "start_timestamp": T("2024-09-02"),
        "end_timestamp": T("2024-09-03"),
    }
    return orders_factory([{"order_id": "100"}, {**base_second, **second}])


def test_transition_types(orders_factory: Callable[..., pd.DataFrame]) -> None:
    cases: list[tuple[dict, str]] = [
        ({}, "same_product_same_recipe"),
        ({"recipe_version": "v2"}, "same_product_recipe_change"),
        ({"bom_signature": "sig-b"}, "composition_change"),
        ({"product_code": "214"}, "product_change"),
        ({"start_timestamp": T("2024-09-01 18:00")}, "overlap_transition"),
        ({"start_timestamp": T("2024-09-02 06:00")}, "gap_transition"),
        ({"product_code": None}, "unknown"),
    ]
    for second, expected in cases:
        trans = aggregate.classify_transitions(_pair(orders_factory, second), 0.0)
        assert len(trans) == 1
        assert trans.loc[0, "transition_type"] == expected, expected


def test_transition_precedence_interval_over_content(
    orders_factory: Callable[..., pd.DataFrame],
) -> None:
    # Overlapping AND product change -> the interval relation wins.
    trans = aggregate.classify_transitions(
        _pair(
            orders_factory,
            {"start_timestamp": T("2024-09-01 18:00"), "product_code": "214"},
        ),
        0.0,
    )
    assert trans.loc[0, "transition_type"] == "overlap_transition"


def test_transition_row_fields(orders_factory: Callable[..., pd.DataFrame]) -> None:
    trans = aggregate.classify_transitions(
        _pair(orders_factory, {"recipe_version": "v2", "bom_signature": "sig-b"}), 0.0
    )
    row = trans.iloc[0]
    assert row["transition_timestamp"] == T("2024-09-02")
    assert row["previous_order_id"] == "100"
    assert row["next_order_id"] == "101"
    assert row["previous_recipe_context_key"] == "114:v1:sig-a"
    assert row["next_recipe_context_key"] == "114:v2:sig-b"


def test_attach_overlaps_backfills_orders(
    orders_factory: Callable[..., pd.DataFrame],
) -> None:
    orders = orders_factory(
        [
            {"order_id": "100"},
            {
                "order_id": "101",
                "start_timestamp": T("2024-09-01 12:00"),
                "end_timestamp": T("2024-09-03"),
            },
            {
                "order_id": "102",
                "start_timestamp": T("2024-09-04"),
                "end_timestamp": T("2024-09-05"),
            },
        ]
    )
    out = aggregate.attach_overlaps(orders, aggregate.detect_overlaps(orders))
    by_id = out.set_index("order_id")
    assert bool(by_id.loc["100", "has_overlap"]) is True
    assert by_id.loc["100", "overlap_order_ids"] == "101"
    assert bool(by_id.loc["102", "has_overlap"]) is False
    assert by_id.loc["102", "overlap_order_ids"] == ""
