"""Stage B — normalize raw BOM rows into the component-level table.

Normalization is conservative by contract: values are trimmed and typed but
never invented, imputed or renormalized. Rows leave the component table only
through the explicit ``rejected`` / ``duplicates`` side tables, each carrying
a reason; a percentage that fails to parse stays in the table as ``NaN``
with a Finding. Recipe totals are NOT normalized to 100%.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from src.context.bom.policy import BomContextPolicy
from src.context.bom.validation import CHECK, parse_percentages, parse_timestamps
from src.preprocessing._common.reporting import Finding, Severity

#: Normalized component schema, in output order (the contract).
COMPONENT_COLUMNS = [
    "order_id",
    "start_timestamp",
    "end_timestamp",
    "product_code",
    "product_name",
    "recipe_version",
    "recipe_description",
    "material_code",
    "material_name",
    "percentage",
    "dosing_point",
    "source_row_number",
    "source_file",
]

_TRACE_COLUMNS = ["source_row_number", "source_file"]
_KEY_COLUMNS = ["order_id", "material_code", "dosing_point"]


@dataclass
class NormalizeResult:
    """Everything Stage B produces."""

    components: pd.DataFrame
    rejected: pd.DataFrame
    duplicates: pd.DataFrame
    findings: list[Finding] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)


def _trimmed_string_frame(raw: pd.DataFrame, policy: BomContextPolicy) -> pd.DataFrame:
    """Rename raw headers to normalized names; trim; blank -> ``NA``."""
    mapping = {v: k for k, v in policy.raw_input.columns.model_dump().items()}
    out = raw.rename(columns=mapping)[
        [c for c in COMPONENT_COLUMNS if c not in _TRACE_COLUMNS] + _TRACE_COLUMNS
    ].copy()
    for col in out.columns:
        if col in _TRACE_COLUMNS:
            continue
        trimmed = out[col].astype("string").str.strip()
        out[col] = trimmed.mask(trimmed == "", pd.NA)
    return out


def _reject_reason(frame: pd.DataFrame) -> pd.Series:
    """First applicable rejection reason per row ('' = keep)."""
    start_raw, end_raw = frame["start_timestamp"], frame["end_timestamp"]
    start_ok = parse_timestamps(start_raw).notna()
    end_ok = parse_timestamps(end_raw).notna()
    reason = pd.Series("", index=frame.index, dtype=str)
    no_window = ~start_ok & ~end_ok
    reason[no_window & (start_raw.notna() | end_raw.notna())] = "unparseable_timestamps"
    reason[no_window & start_raw.isna() & end_raw.isna()] = "missing_timestamps"
    reason[frame["material_code"].isna()] = "missing_material_code"
    reason[frame["order_id"].isna()] = "missing_order_id"
    return reason


def _split_duplicates(
    kept: pd.DataFrame, pct: pd.Series, findings: list[Finding]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Route exact and repeated-component duplicates out of ``kept``."""
    if kept.empty:
        empty = kept.copy()
        empty["duplicate_reason"] = pd.Series(dtype=str)
        return kept, empty
    data_cols = [c for c in kept.columns if c not in _TRACE_COLUMNS]
    exact = kept.duplicated(subset=data_cols, keep="first")

    pct_key = pct.map(lambda v: "null" if pd.isna(v) else format(float(v), ".10g"))
    component_key = kept[_KEY_COLUMNS].astype(str).agg("|".join, axis=1) + "|" + pct_key
    repeated = component_key.duplicated(keep="first") & ~exact

    conflicting = (
        kept[_KEY_COLUMNS].astype(str).agg("|".join, axis=1).duplicated(keep=False)
        & ~exact
        & ~repeated
    )
    if conflicting.any():
        findings.append(
            Finding(
                check=CHECK,
                severity=Severity.IMPORTANT,
                finding_type="component_conflict",
                count=int(conflicting.sum()),
                action_taken="kept_both_rows",
                evidence={
                    "detail": "same (order, material, dosing point) with "
                    "different percentages — kept, flags the order",
                    "source_rows": kept.loc[conflicting, "source_row_number"]
                    .astype(int)
                    .tolist(),
                },
            )
        )

    duplicates = kept[exact | repeated].copy()
    duplicates["duplicate_reason"] = "exact_duplicate"
    duplicates.loc[repeated[exact | repeated].to_numpy(), "duplicate_reason"] = (
        "repeated_component"
    )
    return kept[~exact & ~repeated], duplicates


def normalize(raw: pd.DataFrame, policy: BomContextPolicy) -> NormalizeResult:
    """Raw string frame -> typed components + rejected/duplicate side tables."""
    findings: list[Finding] = []
    frame = _trimmed_string_frame(raw, policy)

    reason = _reject_reason(frame)
    rejected = frame[reason != ""].copy()
    rejected["reject_reason"] = reason[reason != ""]
    kept = frame[reason == ""]
    if len(rejected):
        findings.append(
            Finding(
                check=CHECK,
                severity=Severity.IMPORTANT,
                finding_type="rejected_rows",
                count=len(rejected),
                action_taken="routed_to_rejected_table",
                evidence={
                    "reasons": rejected["reject_reason"].value_counts().to_dict()
                },
            )
        )

    pct = parse_percentages(kept["percentage"], policy.raw_input.decimal_comma)
    kept, duplicates = _split_duplicates(kept, pct, findings)
    if len(duplicates):
        findings.append(
            Finding(
                check=CHECK,
                severity=Severity.IMPORTANT,
                finding_type="duplicate_rows",
                count=len(duplicates),
                action_taken="kept_first_routed_rest",
                evidence={
                    "reasons": duplicates["duplicate_reason"].value_counts().to_dict()
                },
            )
        )

    components = kept.copy()
    components["start_timestamp"] = parse_timestamps(components["start_timestamp"])
    components["end_timestamp"] = parse_timestamps(components["end_timestamp"])
    components["percentage"] = parse_percentages(
        components["percentage"], policy.raw_input.decimal_comma
    )
    pct_failed = int(
        (components["percentage"].isna() & kept["percentage"].notna()).sum()
    )
    if pct_failed:
        findings.append(
            Finding(
                check=CHECK,
                severity=Severity.IMPORTANT,
                finding_type="percentage_kept_as_nan",
                count=pct_failed,
                action_taken="kept_null_no_imputation",
            )
        )

    stats = {
        "raw_row_count": int(len(raw)),
        "component_row_count": int(len(components)),
        "rejected_row_count": int(len(rejected)),
        "duplicate_row_count": int(len(duplicates)),
        "percentage_parse_failures": pct_failed,
    }
    return NormalizeResult(
        components=components[COMPONENT_COLUMNS].reset_index(drop=True),
        rejected=rejected.reset_index(drop=True),
        duplicates=duplicates.reset_index(drop=True),
        findings=findings,
        stats=stats,
    )
