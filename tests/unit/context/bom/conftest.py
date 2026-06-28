"""Fixtures for the BOM Operational Context Layer unit tests.

``raw_bom_factory`` builds frames with the *real* Spanish source headers
(including the ``Fecha Incio`` typo the file actually ships) so every test
exercises the config-driven column mapping. ``orders_factory`` builds small
Stage C-shaped order frames for the interval/timeline tests.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pandas as pd
import pytest
from src.config import PROJECT_ROOT
from src.context.bom.policy import BomContextPolicy, load_policy

#: Real source headers — incl. the "Fecha Incio" typo present in the file.
RAW_HEADERS = [
    "EQ56_ORDRE",
    "Fecha Incio",
    "Fecha Fin",
    "Producto",
    "Descripcion Producto",
    "Version",
    "Descripcion version",
    "Materia prima",
    "Descripcion materia prima",
    "Porcentaje",
    "Punto Dosificacion",
]

_RAW_DEFAULTS: dict[str, str] = {
    "order_id": "100",
    "start_timestamp": "2024-09-01 00:00:00",
    "end_timestamp": "2024-09-02 00:00:00",
    "product_code": "114",
    "product_name": "CC-21",
    "recipe_version": "v1",
    "recipe_description": "recipe one",
    "material_code": "1222",
    "material_name": "HARINILLA DE MAIZ",
    "percentage": "60,5",
    "dosing_point": "PP",
}

_NORMALIZED_TO_RAW = dict(zip(_RAW_DEFAULTS.keys(), RAW_HEADERS, strict=True))


@pytest.fixture(scope="session")
def bom_policy() -> BomContextPolicy:
    """Real policy loaded from configs/bom_context.yaml."""
    return load_policy(PROJECT_ROOT / "configs" / "bom_context.yaml")


@pytest.fixture
def raw_bom_factory() -> Callable[..., pd.DataFrame]:
    """Factory: list of normalized-key override dicts -> raw-header frame."""

    def _make(rows: list[dict[str, Any]] | None = None) -> pd.DataFrame:
        rows = rows if rows is not None else [{}]
        records = []
        for overrides in rows:
            merged = {**_RAW_DEFAULTS, **overrides}
            records.append({_NORMALIZED_TO_RAW[k]: v for k, v in merged.items()})
        frame = pd.DataFrame(records, columns=RAW_HEADERS)
        frame["source_row_number"] = range(1, len(frame) + 1)
        frame["source_file"] = "test.csv"
        return frame

    return _make


_ORDER_DEFAULTS: dict[str, Any] = {
    "order_id": "100",
    "start_timestamp": pd.Timestamp("2024-09-01 00:00:00"),
    "end_timestamp": pd.Timestamp("2024-09-02 00:00:00"),
    "product_code": "114",
    "product_name": "CC-21",
    "recipe_version": "v1",
    "recipe_description": "recipe one",
    "component_count": 1,
    "unique_material_count": 1,
    "dosing_point_count": 1,
    "total_percentage": 100.0,
    "bom_signature": "sig-a",
    "has_metadata_conflict": False,
    "has_percentage_warning": False,
    "has_overlap": False,
    "overlap_order_ids": "",
}


@pytest.fixture
def orders_factory() -> Callable[..., pd.DataFrame]:
    """Factory: list of override dicts -> Stage C-shaped orders frame."""

    def _make(rows: list[dict[str, Any]]) -> pd.DataFrame:
        records = []
        for overrides in rows:
            row = {**_ORDER_DEFAULTS, **overrides}
            start, end = row["start_timestamp"], row["end_timestamp"]
            row.setdefault(
                "duration_seconds",
                (end - start).total_seconds()
                if pd.notna(start) and pd.notna(end)
                else None,
            )
            row.setdefault(
                "is_valid_window",
                bool(pd.notna(start) and pd.notna(end) and start < end),
            )
            row.setdefault(
                "recipe_context_key",
                ":".join(
                    "null" if pd.isna(row[k]) else str(row[k])
                    for k in ("product_code", "recipe_version", "bom_signature")
                ),
            )
            row.setdefault(
                "context_quality_status",
                "ok" if row["is_valid_window"] else "invalid_window",
            )
            records.append(row)
        return pd.DataFrame(records)

    return _make


@pytest.fixture
def master_ts_factory() -> Callable[..., pd.DatetimeIndex]:
    """Factory for a small, sorted, unique master timestamp index."""

    def _make(
        start: str = "2024-08-31 12:00:00", periods: int = 96, freq: str = "1h"
    ) -> pd.DatetimeIndex:
        idx = pd.DatetimeIndex(pd.date_range(start, periods=periods, freq=freq))
        idx.name = "timestamp"
        return idx

    return _make
