"""Stage C — order aggregation, signature determinism, quality flags."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd
import pytest
from src.context.bom import aggregate, normalize
from src.context.bom.policy import BomContextPolicy


def _components(
    raw_bom_factory: Callable[..., pd.DataFrame],
    policy: BomContextPolicy,
    rows: list[dict],
) -> pd.DataFrame:
    return normalize.normalize(raw_bom_factory(rows), policy).components


def test_signature_is_row_order_invariant(
    raw_bom_factory: Callable[..., pd.DataFrame], bom_policy: BomContextPolicy
) -> None:
    rows = [
        {"material_code": "1222", "percentage": "60,5", "dosing_point": "PP"},
        {"material_code": "1901", "percentage": "39,5", "dosing_point": "DO"},
    ]
    a = _components(raw_bom_factory, bom_policy, rows)
    b = _components(raw_bom_factory, bom_policy, rows[::-1])
    sig_a = aggregate.bom_signature(a, bom_policy.signature)
    sig_b = aggregate.bom_signature(b, bom_policy.signature)
    assert sig_a.loc["100"] == sig_b.loc["100"]


def test_signature_is_format_stable(
    raw_bom_factory: Callable[..., pd.DataFrame], bom_policy: BomContextPolicy
) -> None:
    a = _components(raw_bom_factory, bom_policy, [{"percentage": "37,86"}])
    b = _components(raw_bom_factory, bom_policy, [{"percentage": "37,860"}])
    assert (
        aggregate.bom_signature(a, bom_policy.signature).loc["100"]
        == (aggregate.bom_signature(b, bom_policy.signature).loc["100"])
    )


@pytest.mark.parametrize(
    "override",
    [
        {"percentage": "61,5"},
        {"material_code": "9999"},
        {"dosing_point": "DO"},
    ],
)
def test_signature_changes_when_composition_changes(
    raw_bom_factory: Callable[..., pd.DataFrame],
    bom_policy: BomContextPolicy,
    override: dict,
) -> None:
    base = _components(raw_bom_factory, bom_policy, [{}])
    changed = _components(raw_bom_factory, bom_policy, [override])
    assert (
        aggregate.bom_signature(base, bom_policy.signature).loc["100"]
        != (aggregate.bom_signature(changed, bom_policy.signature).loc["100"])
    )


def test_recipe_context_key_composition(
    raw_bom_factory: Callable[..., pd.DataFrame], bom_policy: BomContextPolicy
) -> None:
    comp = _components(raw_bom_factory, bom_policy, [{}])
    orders, _ = aggregate.aggregate_orders(comp, bom_policy)
    sig = orders.loc[0, "bom_signature"]
    assert orders.loc[0, "recipe_context_key"] == f"114:v1:{sig}"
    assert len(sig) == bom_policy.signature.hash_prefix_len


@pytest.mark.parametrize(
    ("total", "expect_warning"),
    [("98,9", True), ("99,0", False), ("103,0", False), ("103,1", True)],
)
def test_percentage_warning_boundaries(
    raw_bom_factory: Callable[..., pd.DataFrame],
    bom_policy: BomContextPolicy,
    total: str,
    expect_warning: bool,
) -> None:
    comp = _components(raw_bom_factory, bom_policy, [{"percentage": total}])
    orders, _ = aggregate.aggregate_orders(comp, bom_policy)
    assert bool(orders.loc[0, "has_percentage_warning"]) is expect_warning
    assert orders.loc[0, "total_percentage"] == float(total.replace(",", "."))


def test_null_percentage_triggers_warning_not_imputation(
    raw_bom_factory: Callable[..., pd.DataFrame], bom_policy: BomContextPolicy
) -> None:
    comp = _components(raw_bom_factory, bom_policy, [{"percentage": "broken"}])
    orders, _ = aggregate.aggregate_orders(comp, bom_policy)
    assert bool(orders.loc[0, "has_percentage_warning"]) is True
    assert pd.isna(orders.loc[0, "total_percentage"])


def test_metadata_conflict_flagged(
    raw_bom_factory: Callable[..., pd.DataFrame], bom_policy: BomContextPolicy
) -> None:
    comp = _components(
        raw_bom_factory,
        bom_policy,
        [
            {"material_code": "1", "percentage": "60,5"},
            {"material_code": "2", "percentage": "39,5", "recipe_version": "v2"},
        ],
    )
    orders, findings = aggregate.aggregate_orders(comp, bom_policy)
    assert bool(orders.loc[0, "has_metadata_conflict"]) is True
    assert orders.loc[0, "context_quality_status"] == "metadata_conflict"
    assert any(f.finding_type == "orders_with_metadata_conflict" for f in findings)


def test_order_counts(
    raw_bom_factory: Callable[..., pd.DataFrame], bom_policy: BomContextPolicy
) -> None:
    comp = _components(
        raw_bom_factory,
        bom_policy,
        [
            {"material_code": "1", "percentage": "50,0", "dosing_point": "PP"},
            {"material_code": "2", "percentage": "30,0", "dosing_point": "PP"},
            {"material_code": "3", "percentage": "20,0", "dosing_point": "DO"},
        ],
    )
    orders, _ = aggregate.aggregate_orders(comp, bom_policy)
    row = orders.iloc[0]
    assert row["component_count"] == 3
    assert row["unique_material_count"] == 3
    assert row["dosing_point_count"] == 2
    assert row["total_percentage"] == 100.0
    assert row["duration_seconds"] == 86400.0
    assert row["context_quality_status"] == "ok"


def test_invalid_window_and_multiple_flags(
    raw_bom_factory: Callable[..., pd.DataFrame], bom_policy: BomContextPolicy
) -> None:
    comp = _components(
        raw_bom_factory,
        bom_policy,
        [
            {
                "start_timestamp": "2024-09-02 00:00:00",
                "end_timestamp": "2024-09-01 00:00:00",
                "percentage": "10,0",
            }
        ],
    )
    orders, _ = aggregate.aggregate_orders(comp, bom_policy)
    assert bool(orders.loc[0, "is_valid_window"]) is False
    assert orders.loc[0, "context_quality_status"] == "multiple_flags"
