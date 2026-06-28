"""Stage E — master-aligned context timeline."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd
from src.context.bom import timeline, validation

T = pd.Timestamp


def _build(
    orders_factory: Callable[..., pd.DataFrame],
    master_ts_factory: Callable[..., pd.DatetimeIndex],
    specs: list[dict],
    **ts_kwargs: object,
) -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    orders = orders_factory(specs)
    master_ts = master_ts_factory(**ts_kwargs)
    tl, _ = timeline.build_context_timeline(orders, master_ts)
    validation.validate_timeline(tl, master_ts, expected_rows=len(master_ts))
    return tl, master_ts


def test_one_row_per_master_timestamp(
    orders_factory: Callable[..., pd.DataFrame],
    master_ts_factory: Callable[..., pd.DatetimeIndex],
) -> None:
    tl, master_ts = _build(orders_factory, master_ts_factory, [{}])
    assert len(tl) == len(master_ts)
    assert (tl["timestamp"].to_numpy() == master_ts.to_numpy()).all()


def test_matched_single_order_fills_scalars_and_lists(
    orders_factory: Callable[..., pd.DataFrame],
    master_ts_factory: Callable[..., pd.DatetimeIndex],
) -> None:
    tl, _ = _build(orders_factory, master_ts_factory, [{}])
    row = tl[tl["timestamp"] == T("2024-09-01 12:00")].iloc[0]
    assert row["bom_context_status"] == "matched_single_order"
    assert row["active_order_count"] == 1
    assert row["order_id"] == "100"
    assert row["order_ids"] == "100"
    assert row["recipe_context_key"] == "114:v1:sig-a"
    assert bool(row["has_active_order"]) is True
    assert bool(row["is_transition_overlap"]) is False


def test_half_open_boundary_start_inclusive_end_exclusive(
    orders_factory: Callable[..., pd.DataFrame],
    master_ts_factory: Callable[..., pd.DatetimeIndex],
) -> None:
    tl, _ = _build(orders_factory, master_ts_factory, [{}])
    at_start = tl[tl["timestamp"] == T("2024-09-01 00:00")].iloc[0]
    at_end = tl[tl["timestamp"] == T("2024-09-02 00:00")].iloc[0]
    assert at_start["order_id"] == "100"  # start <= t
    assert pd.isna(at_end["order_id"])  # t < end strictly


def test_overlap_rows_preserve_all_orders_and_null_scalars(
    orders_factory: Callable[..., pd.DataFrame],
    master_ts_factory: Callable[..., pd.DatetimeIndex],
) -> None:
    tl, _ = _build(
        orders_factory,
        master_ts_factory,
        [
            {},
            {
                "order_id": "101",
                "start_timestamp": T("2024-09-01 12:00"),
                "end_timestamp": T("2024-09-03"),
                "recipe_version": "v2",
                "bom_signature": "sig-b",
            },
        ],
    )
    overlap = tl[tl["bom_context_status"] == "transition_overlap"]
    assert len(overlap) == 12  # hourly grid, 12h overlap window
    row = overlap.iloc[0]
    assert pd.isna(row["order_id"])  # never silently pick one
    assert row["order_ids"] == "100|101"  # sorted, pipe-joined
    assert row["recipe_context_keys"] == "114:v1:sig-a|114:v2:sig-b"
    assert row["active_order_count"] == 2
    assert bool(row["is_transition_overlap"]) is True


def test_no_active_order_vs_outside_coverage(
    orders_factory: Callable[..., pd.DataFrame],
    master_ts_factory: Callable[..., pd.DatetimeIndex],
) -> None:
    tl, _ = _build(
        orders_factory,
        master_ts_factory,
        [
            {},
            {
                "order_id": "101",
                "start_timestamp": T("2024-09-03"),
                "end_timestamp": T("2024-09-04"),
            },
        ],
        periods=144,
    )
    before = tl[tl["timestamp"] == T("2024-08-31 18:00")].iloc[0]
    inside_gap = tl[tl["timestamp"] == T("2024-09-02 12:00")].iloc[0]
    after = tl[tl["timestamp"] == T("2024-09-05 00:00")].iloc[0]
    assert before["bom_context_status"] == "outside_bom_coverage"
    assert inside_gap["bom_context_status"] == "no_active_order"
    assert after["bom_context_status"] == "outside_bom_coverage"
    assert before["order_ids"] == ""


def test_invalid_window_marks_span(
    orders_factory: Callable[..., pd.DataFrame],
    master_ts_factory: Callable[..., pd.DatetimeIndex],
) -> None:
    tl, _ = _build(
        orders_factory,
        master_ts_factory,
        [
            {},
            {
                "order_id": "101",
                "start_timestamp": T("2024-09-02 06:00"),
                "end_timestamp": T("2024-09-02 03:00"),  # inverted
            },
        ],
    )
    span = tl[
        (tl["timestamp"] >= T("2024-09-02 03:00"))
        & (tl["timestamp"] < T("2024-09-02 06:00"))
    ]
    assert (span["bom_context_status"] == "invalid_window").all()


def test_first_order_position_zero_assignment(
    orders_factory: Callable[..., pd.DataFrame],
    master_ts_factory: Callable[..., pd.DatetimeIndex],
) -> None:
    # Guards the 1-based position-sum trick: position 0 must be assignable.
    tl, _ = _build(orders_factory, master_ts_factory, [{"order_id": "777"}])
    matched = tl[tl["bom_context_status"] == "matched_single_order"]
    assert (matched["order_id"] == "777").all()


def test_no_valid_orders_everything_outside(
    orders_factory: Callable[..., pd.DataFrame],
    master_ts_factory: Callable[..., pd.DatetimeIndex],
) -> None:
    orders = orders_factory([{"start_timestamp": pd.NaT, "end_timestamp": pd.NaT}])
    master_ts = master_ts_factory(periods=5)
    tl, _ = timeline.build_context_timeline(orders, master_ts)
    assert (tl["bom_context_status"] == "outside_bom_coverage").all()
