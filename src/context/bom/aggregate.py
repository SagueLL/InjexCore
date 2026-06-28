"""Stages C, D, F — order aggregation, interval diagnostics, summaries.

Stage C collapses the component table to one row per production order and
attaches the deterministic ``bom_signature`` / ``recipe_context_key``
identities. Stage D sweeps the order boundaries once to find every overlap
window, every gap inside coverage, and the classified order-to-order
transitions. Stage F renders the product / recipe / signature / coverage
summary tables. Nothing here resolves an overlap or normalizes a total —
conflicts are flagged, never repaired.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Any

import pandas as pd

from src.context.bom.policy import BomContextPolicy, SignaturePolicy
from src.context.bom.validation import CHECK, TIMELINE_STATUSES
from src.preprocessing._common.reporting import Finding, Severity

#: Closed vocabulary of transition types (the contract, not a tunable).
TRANSITION_TYPES = (
    "same_product_same_recipe",
    "same_product_recipe_change",
    "product_change",
    "composition_change",
    "overlap_transition",
    "gap_transition",
    "unknown",
)

_LIST_SEP = "|"

_META_COLUMNS = [
    "start_timestamp",
    "end_timestamp",
    "product_code",
    "product_name",
    "recipe_version",
    "recipe_description",
]


def pipe_join(values: Iterable[Any]) -> str:
    """Sorted, unique, pipe-joined representation of list-valued fields."""
    return _LIST_SEP.join(sorted({str(v) for v in values if pd.notna(v)}))


def format_percentage(value: float, fmt: str) -> str:
    """Stable numeric formatting inside the signature hash; NaN -> 'null'."""
    return "null" if pd.isna(value) else format(float(value), fmt)


def bom_signature(components: pd.DataFrame, policy: SignaturePolicy) -> pd.Series:
    """Deterministic composition fingerprint per order.

    sha256 over the lexicographically sorted ``material|dosing|percentage``
    tuples — row order in the source and float-repr noise cannot change it;
    any effective composition change does.
    """
    comp = components.assign(
        _pct=components["percentage"].map(
            lambda v: format_percentage(v, policy.percentage_format)
        ),
        _mat=components["material_code"].astype(str).str.strip(),
        _dos=components["dosing_point"].astype(str).str.strip(),
    )
    canonical = (
        comp.assign(_tup=comp["_mat"] + "|" + comp["_dos"] + "|" + comp["_pct"])
        .sort_values(["order_id", "_tup"])
        .groupby("order_id")["_tup"]
        .agg(";".join)
    )
    return canonical.map(
        lambda s: hashlib.sha256(s.encode("utf-8")).hexdigest()[
            : policy.hash_prefix_len
        ]
    ).rename("bom_signature")


def _modal(series: pd.Series) -> Any:
    """Most frequent non-null value (deterministic tie-break), else ``None``."""
    modes = series.mode(dropna=True)
    return modes.iloc[0] if len(modes) else None


def _context_key(row: pd.Series) -> str:
    parts = (row["product_code"], row["recipe_version"], row["bom_signature"])
    return ":".join("null" if pd.isna(p) else str(p) for p in parts)


def aggregate_orders(
    components: pd.DataFrame, policy: BomContextPolicy
) -> tuple[pd.DataFrame, list[Finding]]:
    """Stage C: one row per production order, with quality flags."""
    grouped = components.groupby("order_id", sort=True)
    orders = grouped[_META_COLUMNS].agg(_modal)
    conflicts = grouped[_META_COLUMNS].nunique(dropna=True)
    orders["has_metadata_conflict"] = (conflicts > 1).any(axis=1)

    orders["duration_seconds"] = (
        orders["end_timestamp"] - orders["start_timestamp"]
    ).dt.total_seconds()
    orders["component_count"] = grouped.size()
    orders["unique_material_count"] = grouped["material_code"].nunique(dropna=True)
    orders["dosing_point_count"] = grouped["dosing_point"].nunique(dropna=True)
    orders["total_percentage"] = grouped["percentage"].sum(min_count=1)
    orders["has_null_percentage"] = grouped["percentage"].agg(
        lambda s: bool(s.isna().any())
    )

    orders = orders.join(bom_signature(components, policy.signature))
    orders = orders.reset_index().rename(columns={"index": "order_id"})
    orders["recipe_context_key"] = orders.apply(_context_key, axis=1)

    pct = policy.percentage
    orders["has_percentage_warning"] = (
        (orders["total_percentage"] < pct.expected_min)
        | (orders["total_percentage"] > pct.expected_max)
        | orders["total_percentage"].isna()
        | orders["has_null_percentage"]
    )
    orders["is_valid_window"] = (
        orders["start_timestamp"].notna()
        & orders["end_timestamp"].notna()
        & (orders["start_timestamp"] < orders["end_timestamp"])
    )
    orders["context_quality_status"] = _quality_status(orders)
    orders["has_overlap"] = False  # filled by attach_overlaps
    orders["overlap_order_ids"] = ""
    return orders.drop(columns=["has_null_percentage"]), _order_findings(orders)


def _quality_status(orders: pd.DataFrame) -> pd.Series:
    flags = pd.DataFrame(
        {
            "invalid_window": ~orders["is_valid_window"],
            "metadata_conflict": orders["has_metadata_conflict"],
            "percentage_warning": orders["has_percentage_warning"],
        }
    )
    n_flags = flags.sum(axis=1)
    status = flags.idxmax(axis=1).where(n_flags == 1, "multiple_flags")
    return status.where(n_flags > 0, "ok").rename("context_quality_status")


def _order_findings(orders: pd.DataFrame) -> list[Finding]:
    findings: list[Finding] = []
    checks = [
        ("orders_with_invalid_window", ~orders["is_valid_window"], Severity.IMPORTANT),
        (
            "orders_with_metadata_conflict",
            orders["has_metadata_conflict"],
            Severity.IMPORTANT,
        ),
        (
            "orders_with_percentage_warning",
            orders["has_percentage_warning"],
            Severity.AWARE,
        ),
    ]
    for ftype, mask, severity in checks:
        if mask.any():
            findings.append(
                Finding(
                    check=CHECK,
                    severity=severity,
                    finding_type=ftype,
                    count=int(mask.sum()),
                    action_taken="flagged_not_repaired",
                    evidence={
                        "order_ids": orders.loc[mask, "order_id"].astype(str).tolist()
                    },
                )
            )
    return findings


def _boundary_events(orders: pd.DataFrame) -> list[tuple[pd.Timestamp, int, int]]:
    """(timestamp, delta, order position) sorted with ends before starts.

    Ends sort before starts at equal timestamps so half-open windows that
    touch (``prev.end == next.start``) never count as overlapping.
    """
    valid = orders[orders["is_valid_window"]]
    events: list[tuple[pd.Timestamp, int, int]] = []
    for pos, row in valid.iterrows():
        events.append((row["start_timestamp"], +1, pos))
        events.append((row["end_timestamp"], -1, pos))
    return sorted(events, key=lambda e: (e[0], e[1]))


def detect_overlaps(orders: pd.DataFrame) -> pd.DataFrame:
    """Stage D: every maximal window where 2+ orders are simultaneously active.

    ``active_order_ids`` is the union of orders active at any point inside
    the window; ``overlap_count`` is the maximum simultaneous count.
    """
    rows: list[dict[str, Any]] = []
    active: set[int] = set()
    members: set[int] = set()
    start: pd.Timestamp | None = None
    max_count = 0
    for ts, delta, pos in _boundary_events(orders):
        if delta > 0:
            active.add(pos)
            if len(active) >= 2 and start is None:
                start, members, max_count = ts, set(active), len(active)
            elif start is not None:
                members.add(pos)
                max_count = max(max_count, len(active))
        else:
            active.discard(pos)
            if start is not None and len(active) < 2:
                rows.append(_overlap_row(orders, start, ts, members, max_count))
                start = None
    return pd.DataFrame(
        rows,
        columns=[
            "overlap_start",
            "overlap_end",
            "duration_seconds",
            "active_order_ids",
            "active_product_codes",
            "active_recipe_context_keys",
            "overlap_count",
        ],
    )


def _overlap_row(
    orders: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    members: set[int],
    max_count: int,
) -> dict[str, Any]:
    sub = orders.loc[sorted(members)]
    return {
        "overlap_start": start,
        "overlap_end": end,
        "duration_seconds": float((end - start).total_seconds()),
        "active_order_ids": pipe_join(sub["order_id"]),
        "active_product_codes": pipe_join(sub["product_code"]),
        "active_recipe_context_keys": pipe_join(sub["recipe_context_key"]),
        "overlap_count": max_count,
    }


def detect_gaps(orders: pd.DataFrame, tolerance_seconds: float) -> pd.DataFrame:
    """Stage D: windows inside BOM coverage where no valid order is active."""
    events = _boundary_events(orders)
    rows: list[dict[str, Any]] = []
    active: set[int] = set()
    gap_start: pd.Timestamp | None = None
    gap_prev: list[int] = []
    last_event = events[-1][0] if events else None
    for ts, delta, pos in events:
        if delta > 0:
            active.add(pos)
            if gap_start is not None:
                seconds = float((ts - gap_start).total_seconds())
                if seconds > tolerance_seconds:
                    rows.append(
                        {
                            "gap_start": gap_start,
                            "gap_end": ts,
                            "duration_seconds": seconds,
                            "previous_order_id": pipe_join(
                                orders.loc[gap_prev, "order_id"]
                            ),
                            "next_order_id": str(orders.loc[pos, "order_id"]),
                        }
                    )
                gap_start = None
        else:
            active.discard(pos)
            if not active and ts != last_event:
                gap_start, gap_prev = ts, [pos]
    return pd.DataFrame(
        rows,
        columns=[
            "gap_start",
            "gap_end",
            "duration_seconds",
            "previous_order_id",
            "next_order_id",
        ],
    )


def classify_transitions(
    orders: pd.DataFrame, tolerance_seconds: float
) -> pd.DataFrame:
    """Stage D: classified change between consecutive (start-sorted) orders."""
    valid = orders[orders["is_valid_window"]].sort_values(
        ["start_timestamp", "order_id"]
    )
    rows: list[dict[str, Any]] = []
    for prev, nxt in zip(
        valid.iloc[:-1].itertuples(), valid.iloc[1:].itertuples(), strict=True
    ):
        rows.append(
            {
                "transition_timestamp": min(prev.end_timestamp, nxt.start_timestamp),
                "previous_order_id": str(prev.order_id),
                "next_order_id": str(nxt.order_id),
                "previous_product_code": prev.product_code,
                "next_product_code": nxt.product_code,
                "previous_recipe_context_key": prev.recipe_context_key,
                "next_recipe_context_key": nxt.recipe_context_key,
                "transition_type": _transition_type(prev, nxt, tolerance_seconds),
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "transition_timestamp",
            "previous_order_id",
            "next_order_id",
            "previous_product_code",
            "next_product_code",
            "previous_recipe_context_key",
            "next_recipe_context_key",
            "transition_type",
        ],
    )


def _transition_type(prev: Any, nxt: Any, tolerance_seconds: float) -> str:
    """Precedence: interval relation first, then content comparison."""
    if nxt.start_timestamp < prev.end_timestamp:
        return "overlap_transition"
    gap = float((nxt.start_timestamp - prev.end_timestamp).total_seconds())
    if gap > tolerance_seconds:
        return "gap_transition"
    fields = ("product_code", "recipe_version", "bom_signature")
    if any(pd.isna(getattr(o, f)) for o in (prev, nxt) for f in fields):
        return "unknown"
    if prev.product_code != nxt.product_code:
        return "product_change"
    if prev.recipe_version != nxt.recipe_version:
        return "same_product_recipe_change"
    if prev.bom_signature != nxt.bom_signature:
        return "composition_change"
    return "same_product_same_recipe"


def attach_overlaps(orders: pd.DataFrame, overlaps: pd.DataFrame) -> pd.DataFrame:
    """Back-fill ``has_overlap`` / ``overlap_order_ids`` from Stage D."""
    partners: dict[str, set[str]] = {}
    for ids in overlaps["active_order_ids"]:
        group = ids.split(_LIST_SEP)
        for oid in group:
            partners.setdefault(oid, set()).update(o for o in group if o != oid)
    out = orders.copy()
    oid_str = out["order_id"].astype(str)
    out["has_overlap"] = oid_str.isin(partners.keys())
    out["overlap_order_ids"] = oid_str.map(lambda o: pipe_join(partners.get(o, set())))
    return out


# --------------------------------------------------------------------------
# Stage F — summaries
# --------------------------------------------------------------------------


def product_summary(orders: pd.DataFrame) -> pd.DataFrame:
    grouped = orders.groupby("product_code", dropna=False)
    out = pd.DataFrame(
        {
            "product_name": grouped["product_name"].agg(_modal),
            "order_count": grouped.size(),
            "total_duration_seconds": grouped["duration_seconds"].sum(min_count=1),
            "first_seen": grouped["start_timestamp"].min(),
            "last_seen": grouped["end_timestamp"].max(),
            "recipe_count": grouped["recipe_version"].nunique(dropna=True),
            "bom_signature_count": grouped["bom_signature"].nunique(dropna=True),
        }
    )
    return out.reset_index()


def recipe_summary(orders: pd.DataFrame) -> pd.DataFrame:
    keys = ["product_code", "recipe_version", "recipe_context_key", "bom_signature"]
    grouped = orders.groupby(keys, dropna=False)
    out = pd.DataFrame(
        {
            "recipe_description": grouped["recipe_description"].agg(_modal),
            "order_count": grouped.size(),
            "total_duration_seconds": grouped["duration_seconds"].sum(min_count=1),
            "first_seen": grouped["start_timestamp"].min(),
            "last_seen": grouped["end_timestamp"].max(),
            "component_count": grouped["component_count"].agg(_modal),
            "total_percentage": grouped["total_percentage"].agg(_modal),
        }
    )
    return out.reset_index()


def signature_summary(orders: pd.DataFrame) -> pd.DataFrame:
    grouped = orders.groupby("bom_signature", dropna=False)
    out = pd.DataFrame(
        {
            "product_codes": grouped["product_code"].agg(pipe_join),
            "recipe_versions": grouped["recipe_version"].agg(pipe_join),
            "order_count": grouped.size(),
            "first_seen": grouped["start_timestamp"].min(),
            "last_seen": grouped["end_timestamp"].max(),
        }
    )
    return out.reset_index()


def coverage_summary(timeline: pd.DataFrame) -> pd.DataFrame:
    counts = (
        timeline["bom_context_status"]
        .value_counts()
        .reindex(sorted(TIMELINE_STATUSES), fill_value=0)
    )
    out = counts.rename("row_count").to_frame()
    out["percentage"] = (counts / len(timeline) * 100.0).round(4)
    return out.reset_index(names="bom_context_status")
