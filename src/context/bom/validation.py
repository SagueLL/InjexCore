"""Stage A raw-quality assessment + hard invariants for the BOM layer.

``assess_raw_quality`` produces the pre-transformation quality picture the
spec gates on (missingness, duplicates, malformed rows, invalid timestamps,
percentage parsing, potential overlaps). ``validate_timeline`` enforces the
master-alignment contract; a violation raises
:class:`BomContextBlockerError` — alignment is never silently degraded.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.context.bom.policy import BomContextPolicy, ColumnMapPolicy
from src.preprocessing._common.reporting import Finding, Severity

CHECK = "bom_context"

#: Closed vocabulary of timeline statuses (the contract, not a tunable).
TIMELINE_STATUSES = frozenset(
    {
        "matched_single_order",
        "transition_overlap",
        "no_active_order",
        "invalid_window",
        "outside_bom_coverage",
    }
)


class BomContextBlockerError(RuntimeError):
    """A blocker gate failed; the run must stop and report, not degrade."""


def check_required_columns(raw: pd.DataFrame, columns: ColumnMapPolicy) -> None:
    """Blocker gate: every mapped raw header must exist in the CSV."""
    required = list(columns.model_dump().values())
    missing = [c for c in required if c not in raw.columns]
    if missing:
        raise BomContextBlockerError(
            f"Raw BOM CSV is missing required columns {missing}; "
            f"present: {list(raw.columns)}"
        )


def _is_blank(s: pd.Series) -> pd.Series:
    """Null or whitespace-only string cells."""
    return s.isna() | (s.astype(str).str.strip() == "")


def parse_timestamps(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce")


def parse_percentages(s: pd.Series, decimal_comma: bool) -> pd.Series:
    cleaned = s.astype(str).str.strip()
    if decimal_comma:
        cleaned = cleaned.str.replace(",", ".", regex=False)
    return pd.to_numeric(cleaned, errors="coerce")


def _order_window_stats(raw: pd.DataFrame, cols: ColumnMapPolicy) -> dict[str, Any]:
    """Per-order window checks on the raw frame (start>=end, overlap pairs)."""
    frame = pd.DataFrame(
        {
            "order_id": raw[cols.order_id],
            "start": parse_timestamps(raw[cols.start_timestamp]),
            "end": parse_timestamps(raw[cols.end_timestamp]),
        }
    )
    orders = frame.groupby("order_id", dropna=True).agg(
        start=("start", "min"), end=("end", "max")
    )
    valid = orders.dropna()
    inverted = valid[valid["start"] >= valid["end"]]
    windows = valid[valid["start"] < valid["end"]].sort_values("start")
    starts = windows["start"].to_numpy()
    ends = windows["end"].to_numpy()
    overlap_pairs = sum(
        int((starts[i + 1 :] < ends[i]).sum()) for i in range(len(windows))
    )
    return {
        "order_count": int(orders.shape[0]),
        "orders_start_ge_end": sorted(inverted.index.astype(str)),
        "potential_overlap_pairs": overlap_pairs,
        "bom_span_start": str(windows["start"].min()) if len(windows) else None,
        "bom_span_end": str(windows["end"].max()) if len(windows) else None,
    }


def _metadata_conflict_orders(raw: pd.DataFrame, cols: ColumnMapPolicy) -> list[str]:
    """Orders whose product/recipe/window metadata disagrees across rows."""
    meta_cols = [
        cols.start_timestamp,
        cols.end_timestamp,
        cols.product_code,
        cols.recipe_version,
    ]
    nunique = raw.groupby(cols.order_id)[meta_cols].nunique(dropna=True)
    conflicted = nunique[(nunique > 1).any(axis=1)]
    return sorted(conflicted.index.astype(str))


def assess_raw_quality(
    raw: pd.DataFrame, policy: BomContextPolicy
) -> tuple[dict[str, Any], list[Finding]]:
    """Stage A: quality picture of the raw frame before any transformation."""
    cols = policy.raw_input.columns
    data_cols = [
        c for c in raw.columns if c not in ("source_row_number", "source_file")
    ]

    missing = {c: int(_is_blank(raw[c]).sum()) for c in data_cols}
    start_ts = parse_timestamps(raw[cols.start_timestamp])
    end_ts = parse_timestamps(raw[cols.end_timestamp])
    bad_start = int((start_ts.isna() & ~_is_blank(raw[cols.start_timestamp])).sum())
    bad_end = int((end_ts.isna() & ~_is_blank(raw[cols.end_timestamp])).sum())
    pct = parse_percentages(raw[cols.percentage], policy.raw_input.decimal_comma)
    pct_failures = int((pct.isna() & ~_is_blank(raw[cols.percentage])).sum())
    pct_outliers = int((pct > policy.percentage.outlier_row_max).sum())

    stats: dict[str, Any] = {
        "row_count": int(len(raw)),
        "column_count": len(data_cols),
        "columns": data_cols,
        "encoding": policy.raw_input.encoding,
        "delimiter": policy.raw_input.delimiter,
        "decimal_comma": policy.raw_input.decimal_comma,
        "timestamp_sample": str(raw[cols.start_timestamp].iloc[0])
        if len(raw)
        else None,
        "missing_by_column": missing,
        "duplicate_row_count": int(raw.duplicated(subset=data_cols).sum()),
        "invalid_start_timestamps": bad_start,
        "invalid_end_timestamps": bad_end,
        "percentage_parse_failures": pct_failures,
        "percentage_outlier_rows": pct_outliers,
        "unique_orders": int(raw[cols.order_id].nunique(dropna=True)),
        "unique_products": int(raw[cols.product_code].nunique(dropna=True)),
        "unique_recipe_versions": int(raw[cols.recipe_version].nunique(dropna=True)),
        "unique_materials": int(raw[cols.material_code].nunique(dropna=True)),
        "unique_dosing_points": int(raw[cols.dosing_point].nunique(dropna=True)),
        "metadata_conflict_orders": _metadata_conflict_orders(raw, cols),
        **_order_window_stats(raw, cols),
    }
    return stats, _raw_quality_findings(stats)


def _raw_quality_findings(stats: dict[str, Any]) -> list[Finding]:
    """Findings for every non-clean Stage A statistic."""
    findings: list[Finding] = []

    def add(severity: Severity, ftype: str, count: int, **evidence: Any) -> None:
        findings.append(
            Finding(
                check=CHECK,
                severity=severity,
                finding_type=ftype,
                count=count,
                action_taken="report_only",
                evidence=evidence,
            )
        )

    if stats["duplicate_row_count"]:
        add(Severity.IMPORTANT, "duplicate_raw_rows", stats["duplicate_row_count"])
    bad_ts = stats["invalid_start_timestamps"] + stats["invalid_end_timestamps"]
    if bad_ts:
        add(Severity.IMPORTANT, "invalid_timestamps", bad_ts)
    if stats["percentage_parse_failures"]:
        add(
            Severity.IMPORTANT,
            "percentage_parse_failures",
            stats["percentage_parse_failures"],
        )
    if stats["percentage_outlier_rows"]:
        add(Severity.AWARE, "percentage_outlier_rows", stats["percentage_outlier_rows"])
    if stats["orders_start_ge_end"]:
        add(
            Severity.IMPORTANT,
            "orders_start_ge_end",
            len(stats["orders_start_ge_end"]),
            order_ids=stats["orders_start_ge_end"],
        )
    if stats["metadata_conflict_orders"]:
        add(
            Severity.IMPORTANT,
            "orders_with_metadata_conflicts",
            len(stats["metadata_conflict_orders"]),
            order_ids=stats["metadata_conflict_orders"],
        )
    if stats["potential_overlap_pairs"]:
        add(
            Severity.AWARE,
            "potential_order_overlaps",
            stats["potential_overlap_pairs"],
        )
    missing_total = sum(stats["missing_by_column"].values())
    if missing_total:
        add(
            Severity.AWARE,
            "missing_values",
            missing_total,
            by_column={k: v for k, v in stats["missing_by_column"].items() if v},
        )
    return findings


def assess_coverage(
    orders: pd.DataFrame, master_ts: pd.DatetimeIndex
) -> tuple[dict[str, Any], list[Finding]]:
    """BOM order-window coverage relative to the master timeline span."""
    valid = orders.dropna(subset=["start_timestamp", "end_timestamp"])
    valid = valid[valid["start_timestamp"] < valid["end_timestamp"]]
    outside = valid[
        (valid["end_timestamp"] <= master_ts.min())
        | (valid["start_timestamp"] > master_ts.max())
    ]
    stats = {
        "master_span_start": str(master_ts.min()),
        "master_span_end": str(master_ts.max()),
        "bom_span_start": str(valid["start_timestamp"].min()) if len(valid) else None,
        "bom_span_end": str(valid["end_timestamp"].max()) if len(valid) else None,
        "orders_outside_master_span": sorted(outside["order_id"].astype(str)),
    }
    findings: list[Finding] = []
    if len(outside):
        findings.append(
            Finding(
                check=CHECK,
                severity=Severity.AWARE,
                finding_type="orders_outside_master_span",
                count=len(outside),
                action_taken="report_only",
                evidence={"order_ids": stats["orders_outside_master_span"]},
            )
        )
    return stats, findings


def validate_timeline(
    timeline: pd.DataFrame,
    master_ts: pd.DatetimeIndex,
    expected_rows: int | None,
) -> None:
    """Hard alignment invariants; raises :class:`BomContextBlockerError`.

    * exactly one row per master timestamp, identical and ordered;
    * row count matches ``expected_master_rows`` when configured;
    * status vocabulary is closed;
    * scalar context columns are null wherever ``active_order_count != 1``.
    """
    if expected_rows is not None and len(timeline) != expected_rows:
        raise BomContextBlockerError(
            f"Timeline has {len(timeline)} rows, expected {expected_rows}"
        )
    if len(timeline) != len(master_ts):
        raise BomContextBlockerError(
            f"Timeline has {len(timeline)} rows, master has {len(master_ts)}"
        )
    if not (timeline["timestamp"].to_numpy() == master_ts.to_numpy()).all():
        raise BomContextBlockerError("Timeline timestamps differ from the master's")
    bad_status = set(timeline["bom_context_status"].unique()) - TIMELINE_STATUSES
    if bad_status:
        raise BomContextBlockerError(f"Unknown timeline statuses: {sorted(bad_status)}")
    not_single = timeline["active_order_count"] != 1
    for col in ("order_id", "product_code", "recipe_version", "bom_signature"):
        leaked = int(timeline.loc[not_single, col].notna().sum())
        if leaked:
            raise BomContextBlockerError(
                f"Scalar column {col!r} set on {leaked} rows without exactly "
                "one active order — overlap rows must never pick one order"
            )
