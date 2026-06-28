"""Stage E + G — master-aligned context timeline and forensic event windows.

Stage E aligns the order intervals against every master timestamp with a
vectorized boundary sweep (``searchsorted`` + difference arrays — no
row-by-row Python over the 167k master rows). The join policy is explicit:

* 0 active orders  -> ``no_active_order`` / ``outside_bom_coverage``
* 1 active order   -> ``matched_single_order`` (scalar columns filled)
* 2+ active orders -> ``transition_overlap`` — scalar columns stay null and
  every matching order is preserved in the pipe-joined list columns; one
  order is never silently chosen.

Windows are half-open: an order is active for ``start <= t < end``.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd

from src.context.bom.aggregate import pipe_join
from src.context.bom.policy import ForensicWindowsPolicy
from src.context.bom.validation import CHECK
from src.preprocessing._common.reporting import Finding, Severity

#: Timeline schema, in output order (the contract).
TIMELINE_COLUMNS = [
    "timestamp",
    "bom_context_status",
    "active_order_count",
    "order_id",
    "order_ids",
    "product_code",
    "product_codes",
    "recipe_version",
    "recipe_versions",
    "recipe_context_key",
    "recipe_context_keys",
    "bom_signature",
    "bom_signatures",
    "is_transition_overlap",
    "has_active_order",
]

_SCALAR_TO_LIST = {
    "order_id": "order_ids",
    "product_code": "product_codes",
    "recipe_version": "recipe_versions",
    "recipe_context_key": "recipe_context_keys",
    "bom_signature": "bom_signatures",
}


def _ns(value: Any) -> int:
    """Epoch nanoseconds of a timestamp-like value (resolution-safe)."""
    return int(pd.Timestamp(value).as_unit("ns").value)


def _interval_indices(
    valid: pd.DataFrame, ts_ns: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Half-open ``[i0, i1)`` master-row ranges per valid order."""
    starts = valid["start_timestamp"].to_numpy(dtype="datetime64[ns]").view("int64")
    ends = valid["end_timestamp"].to_numpy(dtype="datetime64[ns]").view("int64")
    i0 = np.searchsorted(ts_ns, starts, side="left")
    i1 = np.searchsorted(ts_ns, ends, side="left")
    return i0, i1


def _active_counts_and_single(
    i0: np.ndarray, i1: np.ndarray, n_rows: int
) -> tuple[np.ndarray, np.ndarray]:
    """Per-row active-order count + (count==1) order position via diff arrays."""
    k = len(i0)
    diff_cnt = np.zeros(n_rows + 1, dtype=np.int64)
    np.add.at(diff_cnt, i0, 1)
    np.add.at(diff_cnt, i1, -1)
    active_count = np.cumsum(diff_cnt[:-1])

    pos1 = np.arange(1, k + 1, dtype=np.int64)
    diff_pos = np.zeros(n_rows + 1, dtype=np.int64)
    np.add.at(diff_pos, i0, pos1)
    np.add.at(diff_pos, i1, -pos1)
    pos_sum = np.cumsum(diff_pos[:-1])
    # Where exactly one order is active the position sum IS that order's
    # 1-based position; everywhere else the value is meaningless and unused.
    return active_count, pos_sum - 1


def _overlap_membership(
    i0: np.ndarray, i1: np.ndarray, overlap_rows: np.ndarray
) -> dict[int, list[int]]:
    """Master-row index -> positions of every order active there (2+ rows)."""
    members: dict[int, list[int]] = defaultdict(list)
    for pos in range(len(i0)):
        inside = overlap_rows[(overlap_rows >= i0[pos]) & (overlap_rows < i1[pos])]
        for row in inside:
            members[int(row)].append(pos)
    return members


def _statuses(
    active_count: np.ndarray,
    ts_ns: np.ndarray,
    valid: pd.DataFrame,
    invalid: pd.DataFrame,
) -> np.ndarray:
    """Status per master row, including the invalid-window override."""
    status = np.full(len(ts_ns), "no_active_order", dtype=object)
    if len(valid):
        lo = _ns(valid["start_timestamp"].min())
        hi = _ns(valid["end_timestamp"].max())
        outside = (ts_ns < lo) | (ts_ns >= hi)
    else:
        outside = np.ones(len(ts_ns), dtype=bool)
    status[(active_count == 0) & outside] = "outside_bom_coverage"
    status[active_count == 1] = "matched_single_order"
    status[active_count >= 2] = "transition_overlap"

    both_bounds = invalid.dropna(subset=["start_timestamp", "end_timestamp"])
    for _, row in both_bounds.iterrows():
        lo, hi = sorted((_ns(row["start_timestamp"]), _ns(row["end_timestamp"])))
        in_span = (ts_ns >= lo) & (ts_ns < hi)
        status[in_span & (active_count == 0)] = "invalid_window"
    return status


def build_context_timeline(
    orders: pd.DataFrame,
    master_ts: pd.DatetimeIndex,
    expected_master_rows: int | None = None,
) -> tuple[pd.DataFrame, list[Finding]]:
    """Stage E: exactly one context row per master timestamp."""
    del expected_master_rows  # enforced by validation.validate_timeline
    valid = orders[orders["is_valid_window"]].reset_index(drop=True)
    invalid = orders[~orders["is_valid_window"]]
    ts_ns = master_ts.as_unit("ns").asi8
    n = len(ts_ns)

    i0, i1 = _interval_indices(valid, ts_ns)
    active_count, single_pos = _active_counts_and_single(i0, i1, n)
    status = _statuses(active_count, ts_ns, valid, invalid)

    timeline = pd.DataFrame({"timestamp": master_ts.to_numpy()})
    timeline["bom_context_status"] = status
    timeline["active_order_count"] = active_count

    single = active_count == 1
    for scalar_col, list_col in _SCALAR_TO_LIST.items():
        values = valid[scalar_col].to_numpy(dtype=object)
        scalar = np.full(n, None, dtype=object)
        scalar[single] = values[single_pos[single]]
        timeline[scalar_col] = scalar
        as_list = np.full(n, "", dtype=object)
        as_list[single] = [
            "" if v is None or pd.isna(v) else str(v) for v in scalar[single]
        ]
        timeline[list_col] = as_list

    overlap_rows = np.flatnonzero(active_count >= 2)
    members = _overlap_membership(i0, i1, overlap_rows)
    for row, positions in members.items():
        sub = valid.iloc[positions]
        for scalar_col, list_col in _SCALAR_TO_LIST.items():
            timeline.at[row, list_col] = pipe_join(sub[scalar_col])

    timeline["is_transition_overlap"] = active_count >= 2
    timeline["has_active_order"] = active_count >= 1
    return timeline[TIMELINE_COLUMNS], _timeline_findings(timeline)


def _timeline_findings(timeline: pd.DataFrame) -> list[Finding]:
    findings: list[Finding] = []
    counts = timeline["bom_context_status"].value_counts()
    for status in ("transition_overlap", "no_active_order", "invalid_window"):
        n = int(counts.get(status, 0))
        if n:
            findings.append(
                Finding(
                    check=CHECK,
                    severity=Severity.AWARE,
                    finding_type=f"timeline_{status}_rows",
                    count=n,
                    action_taken="preserved_not_resolved",
                )
            )
    return findings


# --------------------------------------------------------------------------
# Stage G — forensic event windows
# --------------------------------------------------------------------------


def _intersecting(
    frame: pd.DataFrame,
    start_col: str,
    end_col: str,
    lo: pd.Timestamp,
    hi: pd.Timestamp,
) -> pd.DataFrame:
    return frame[(frame[start_col] < hi) & (frame[end_col] > lo)]


def _describe_transitions(transitions: pd.DataFrame) -> str:
    return pipe_join(
        f"{row.transition_timestamp.isoformat()}={row.transition_type}"
        for row in transitions.itertuples()
    )


def event_windows(
    orders: pd.DataFrame,
    transitions: pd.DataFrame,
    overlaps: pd.DataFrame,
    gaps: pd.DataFrame,
    components: pd.DataFrame,
    policy: ForensicWindowsPolicy,
) -> pd.DataFrame:
    """Stage G: BOM activity around each forensic candidate date."""
    valid = orders[orders["is_valid_window"]]
    focus_material_orders = set(
        components.loc[
            components["material_code"]
            .astype(str)
            .isin([str(m) for m in policy.focus_material_codes]),
            "order_id",
        ].astype(str)
    )
    window = pd.Timedelta(hours=policy.window_hours)
    rows: list[dict[str, Any]] = []
    for date in policy.candidate_dates:
        candidate = pd.Timestamp(date)
        lo, hi = candidate - window, candidate + window
        active = _intersecting(valid, "start_timestamp", "end_timestamp", lo, hi)
        near_tr = transitions[
            (transitions["transition_timestamp"] >= lo)
            & (transitions["transition_timestamp"] < hi)
        ]
        near_ov = _intersecting(overlaps, "overlap_start", "overlap_end", lo, hi)
        near_gap = _intersecting(gaps, "gap_start", "gap_end", lo, hi)
        focus_products = (
            active["product_code"]
            .astype(str)
            .isin([str(p) for p in policy.focus_product_codes])
        )
        rows.append(
            {
                "candidate_timestamp": candidate,
                "window_start": lo,
                "window_end": hi,
                "active_order_ids": pipe_join(active["order_id"]),
                "product_codes": pipe_join(active["product_code"]),
                "recipe_versions": pipe_join(active["recipe_version"]),
                "recipe_context_keys": pipe_join(active["recipe_context_key"]),
                "bom_signatures": pipe_join(active["bom_signature"]),
                "nearby_transitions": _describe_transitions(near_tr),
                "nearby_overlaps": pipe_join(
                    f"{r.overlap_start.isoformat()}->{r.overlap_end.isoformat()}"
                    for r in near_ov.itertuples()
                ),
                "nearby_gaps": pipe_join(
                    f"{r.gap_start.isoformat()}->{r.gap_end.isoformat()}"
                    for r in near_gap.itertuples()
                ),
                "focus_product_active": bool(focus_products.any()),
                "focus_material_active": bool(
                    active["order_id"].astype(str).isin(focus_material_orders).any()
                ),
                "context_summary": (
                    f"{len(active)} active order(s), {len(near_tr)} transition(s), "
                    f"{len(near_ov)} overlap(s), {len(near_gap)} gap(s) within "
                    f"±{policy.window_hours}h of {date}"
                ),
            }
        )
    return pd.DataFrame(rows)
