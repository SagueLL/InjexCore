"""Stage B — normalization, rejects, duplicates, null preservation."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd
from src.context.bom import normalize
from src.context.bom.normalize import COMPONENT_COLUMNS
from src.context.bom.policy import BomContextPolicy


def test_header_mapping_and_types(
    raw_bom_factory: Callable[..., pd.DataFrame], bom_policy: BomContextPolicy
) -> None:
    res = normalize.normalize(raw_bom_factory(), bom_policy)
    comp = res.components
    assert list(comp.columns) == COMPONENT_COLUMNS  # typo never leaves the config
    assert comp.loc[0, "order_id"] == "100"
    assert comp.loc[0, "start_timestamp"] == pd.Timestamp("2024-09-01 00:00:00")
    assert comp.loc[0, "percentage"] == 60.5  # "60,5" comma decimal
    assert comp.loc[0, "source_row_number"] == 1


def test_whitespace_trimmed_but_values_preserved(
    raw_bom_factory: Callable[..., pd.DataFrame], bom_policy: BomContextPolicy
) -> None:
    res = normalize.normalize(
        raw_bom_factory([{"product_name": "  CC-21  ", "percentage": " 37,86 "}]),
        bom_policy,
    )
    assert res.components.loc[0, "product_name"] == "CC-21"
    assert res.components.loc[0, "percentage"] == 37.86


def test_unparseable_percentage_kept_as_nan_with_finding(
    raw_bom_factory: Callable[..., pd.DataFrame], bom_policy: BomContextPolicy
) -> None:
    res = normalize.normalize(
        raw_bom_factory([{"percentage": "not-a-number"}]), bom_policy
    )
    assert len(res.components) == 1  # never dropped
    assert pd.isna(res.components.loc[0, "percentage"])  # never imputed
    assert any(f.finding_type == "percentage_kept_as_nan" for f in res.findings)


def test_missing_order_id_rejected_with_reason(
    raw_bom_factory: Callable[..., pd.DataFrame], bom_policy: BomContextPolicy
) -> None:
    res = normalize.normalize(raw_bom_factory([{}, {"order_id": "   "}]), bom_policy)
    assert len(res.components) == 1
    assert len(res.rejected) == 1
    assert res.rejected.loc[0, "reject_reason"] == "missing_order_id"
    assert res.rejected.loc[0, "source_row_number"] == 2


def test_unparseable_timestamps_rejected(
    raw_bom_factory: Callable[..., pd.DataFrame], bom_policy: BomContextPolicy
) -> None:
    res = normalize.normalize(
        raw_bom_factory(
            [{"start_timestamp": "garbage", "end_timestamp": "also garbage"}]
        ),
        bom_policy,
    )
    assert len(res.components) == 0
    assert res.rejected.loc[0, "reject_reason"] == "unparseable_timestamps"


def test_single_bad_timestamp_is_kept_not_rejected(
    raw_bom_factory: Callable[..., pd.DataFrame], bom_policy: BomContextPolicy
) -> None:
    res = normalize.normalize(
        raw_bom_factory([{"start_timestamp": "garbage"}]), bom_policy
    )
    assert len(res.components) == 1
    assert pd.isna(res.components.loc[0, "start_timestamp"])


def test_exact_duplicates_routed_first_kept(
    raw_bom_factory: Callable[..., pd.DataFrame], bom_policy: BomContextPolicy
) -> None:
    res = normalize.normalize(raw_bom_factory([{}, {}, {}]), bom_policy)
    assert len(res.components) == 1
    assert len(res.duplicates) == 2
    assert set(res.duplicates["duplicate_reason"]) == {"exact_duplicate"}
    assert res.components.loc[0, "source_row_number"] == 1


def test_repeated_component_same_percentage_routed(
    raw_bom_factory: Callable[..., pd.DataFrame], bom_policy: BomContextPolicy
) -> None:
    res = normalize.normalize(
        raw_bom_factory([{}, {"material_name": "ALT NAME"}]), bom_policy
    )
    assert len(res.components) == 1
    assert res.duplicates.loc[0, "duplicate_reason"] == "repeated_component"


def test_conflicting_percentages_kept_with_finding(
    raw_bom_factory: Callable[..., pd.DataFrame], bom_policy: BomContextPolicy
) -> None:
    res = normalize.normalize(raw_bom_factory([{}, {"percentage": "39,5"}]), bom_policy)
    assert len(res.components) == 2  # both kept — never merged silently
    assert any(f.finding_type == "component_conflict" for f in res.findings)


def test_totals_never_renormalized(
    raw_bom_factory: Callable[..., pd.DataFrame], bom_policy: BomContextPolicy
) -> None:
    res = normalize.normalize(
        raw_bom_factory(
            [
                {"percentage": "80,0", "material_code": "1"},
                {"percentage": "45,0", "material_code": "2"},
            ]
        ),
        bom_policy,
    )
    assert res.components["percentage"].sum() == 125.0  # preserved as found
