"""Stage A quality assessment + timeline alignment invariants."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd
import pytest
from src.context.bom import validation
from src.context.bom.policy import BomContextPolicy
from src.context.bom.validation import BomContextBlockerError


def test_missing_required_column_is_a_blocker(
    raw_bom_factory: Callable[..., pd.DataFrame], bom_policy: BomContextPolicy
) -> None:
    raw = raw_bom_factory().drop(columns=["Porcentaje"])
    with pytest.raises(BomContextBlockerError, match="Porcentaje"):
        validation.check_required_columns(raw, bom_policy.raw_input.columns)


def test_raw_quality_statistics(
    raw_bom_factory: Callable[..., pd.DataFrame], bom_policy: BomContextPolicy
) -> None:
    raw = raw_bom_factory(
        [
            {},
            {},  # exact duplicate of row 1
            {"order_id": "101", "start_timestamp": "not a date"},
            {"order_id": "102", "percentage": "12%bad"},
            {"order_id": "103", "percentage": "150,0"},
            {
                "order_id": "104",
                "start_timestamp": "2024-09-05 00:00:00",
                "end_timestamp": "2024-09-04 00:00:00",
            },
            # metadata conflict: same order, two products
            {"order_id": "105", "product_code": "114"},
            {"order_id": "105", "product_code": "214"},
        ]
    )
    stats, findings = validation.assess_raw_quality(raw, bom_policy)
    assert stats["row_count"] == 8
    assert stats["duplicate_row_count"] == 1
    assert stats["invalid_start_timestamps"] == 1
    assert stats["percentage_parse_failures"] == 1
    assert stats["percentage_outlier_rows"] == 1
    assert stats["orders_start_ge_end"] == ["104"]
    assert stats["metadata_conflict_orders"] == ["105"]
    types = {f.finding_type for f in findings}
    assert {"duplicate_raw_rows", "invalid_timestamps", "orders_start_ge_end"} <= types


def test_overlap_pair_detection_in_raw_stats(
    raw_bom_factory: Callable[..., pd.DataFrame], bom_policy: BomContextPolicy
) -> None:
    raw = raw_bom_factory(
        [
            {},
            {
                "order_id": "101",
                "start_timestamp": "2024-09-01 12:00:00",
                "end_timestamp": "2024-09-03 00:00:00",
            },
        ]
    )
    stats, _ = validation.assess_raw_quality(raw, bom_policy)
    assert stats["potential_overlap_pairs"] == 1


def _good_timeline(master_ts: pd.DatetimeIndex) -> pd.DataFrame:
    n = len(master_ts)
    return pd.DataFrame(
        {
            "timestamp": master_ts.to_numpy(),
            "bom_context_status": ["no_active_order"] * n,
            "active_order_count": [0] * n,
            "order_id": [None] * n,
            "product_code": [None] * n,
            "recipe_version": [None] * n,
            "bom_signature": [None] * n,
        }
    )


def test_validate_timeline_accepts_aligned_frame(
    master_ts_factory: Callable[..., pd.DatetimeIndex],
) -> None:
    ts = master_ts_factory(periods=10)
    validation.validate_timeline(_good_timeline(ts), ts, expected_rows=10)


def test_validate_timeline_rejects_row_count_mismatch(
    master_ts_factory: Callable[..., pd.DatetimeIndex],
) -> None:
    ts = master_ts_factory(periods=10)
    with pytest.raises(BomContextBlockerError, match="expected 11"):
        validation.validate_timeline(_good_timeline(ts), ts, expected_rows=11)
    with pytest.raises(BomContextBlockerError, match="master has"):
        validation.validate_timeline(_good_timeline(ts).iloc[:-1], ts, None)


def test_validate_timeline_rejects_timestamp_mismatch(
    master_ts_factory: Callable[..., pd.DatetimeIndex],
) -> None:
    ts = master_ts_factory(periods=10)
    shifted = _good_timeline(ts)
    shifted.loc[3, "timestamp"] = shifted.loc[3, "timestamp"] + pd.Timedelta("1s")
    with pytest.raises(BomContextBlockerError, match="differ"):
        validation.validate_timeline(shifted, ts, None)


def test_validate_timeline_rejects_unknown_status(
    master_ts_factory: Callable[..., pd.DatetimeIndex],
) -> None:
    ts = master_ts_factory(periods=10)
    bad = _good_timeline(ts)
    bad.loc[0, "bom_context_status"] = "made_up_status"
    with pytest.raises(BomContextBlockerError, match="made_up_status"):
        validation.validate_timeline(bad, ts, None)


def test_validate_timeline_rejects_scalar_on_overlap_row(
    master_ts_factory: Callable[..., pd.DatetimeIndex],
) -> None:
    ts = master_ts_factory(periods=10)
    bad = _good_timeline(ts)
    bad.loc[0, ["bom_context_status", "active_order_count", "order_id"]] = [
        "transition_overlap",
        2,
        "100",  # scalar must stay null when 2+ orders are active
    ]
    with pytest.raises(BomContextBlockerError, match="never pick"):
        validation.validate_timeline(bad, ts, None)
