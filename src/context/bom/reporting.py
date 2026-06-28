"""Markdown report renderers for the BOM Operational Context Layer.

Two narratives per run: the Stage A raw-quality picture
(``bom_quality_report.md``) and the production-context summary
(``bom_context_report.md``). The structured ``Finding`` list is written
separately via the shared ``write_json`` writer.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.preprocessing._common.reporting import Finding

SCOPE_STATEMENT = (
    "> **Scope:** context engineering only — this layer never modifies the "
    "master dataset, never refits Intelligence-Layer models, and never "
    "changes anomaly thresholds, Behaviour profiles, or the training window."
)


def _kv_table(pairs: list[tuple[str, Any]]) -> list[str]:
    lines = ["| Metric | Value |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in pairs]
    return lines


def _frame_table(frame: pd.DataFrame, max_rows: int = 30) -> list[str]:
    if frame.empty:
        return ["_none_"]
    shown = frame.head(max_rows)
    lines = [
        "| " + " | ".join(map(str, shown.columns)) + " |",
        "|" + "---|" * len(shown.columns),
    ]
    for row in shown.itertuples(index=False):
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    if len(frame) > max_rows:
        lines.append(f"_... {len(frame) - max_rows} more rows in the parquet._")
    return lines


def _findings_section(findings: list[Finding]) -> list[str]:
    if not findings:
        return ["No findings — all checks clean."]
    lines = ["| Severity | Type | Count | Action |", "|---|---|---|---|"]
    lines += [
        f"| {f.severity.value} | {f.finding_type} | {f.count} | {f.action_taken} |"
        for f in findings
    ]
    return lines


def render_quality_report(
    raw_stats: dict[str, Any],
    normalize_stats: dict[str, Any],
    findings: list[Finding],
) -> str:
    """Stage A narrative: parsing, missingness, rejects, duplicates, conflicts."""
    lines = ["# BOM Raw Quality Report", "", SCOPE_STATEMENT, ""]
    lines += ["## Source parsing", ""]
    lines += _kv_table(
        [
            ("Rows (data)", raw_stats["row_count"]),
            ("Columns", raw_stats["column_count"]),
            ("Encoding", raw_stats["encoding"]),
            ("Delimiter", repr(raw_stats["delimiter"])),
            ("Decimal comma", raw_stats["decimal_comma"]),
            ("Timestamp sample", raw_stats["timestamp_sample"]),
        ]
    )
    lines += ["", "## Missingness by column", ""]
    missing = raw_stats["missing_by_column"]
    lines += _kv_table([(k, v) for k, v in missing.items()]) if missing else ["_none_"]
    lines += ["", "## Integrity", ""]
    lines += _kv_table(
        [
            ("Duplicate raw rows", raw_stats["duplicate_row_count"]),
            ("Invalid start timestamps", raw_stats["invalid_start_timestamps"]),
            ("Invalid end timestamps", raw_stats["invalid_end_timestamps"]),
            ("Percentage parse failures", raw_stats["percentage_parse_failures"]),
            ("Percentage outlier rows", raw_stats["percentage_outlier_rows"]),
            ("Orders with start >= end", len(raw_stats["orders_start_ge_end"])),
            (
                "Orders with metadata conflicts",
                len(raw_stats["metadata_conflict_orders"]),
            ),
            ("Potential overlapping order pairs", raw_stats["potential_overlap_pairs"]),
        ]
    )
    lines += ["", "## Cardinality", ""]
    lines += _kv_table(
        [
            ("Unique orders", raw_stats["unique_orders"]),
            ("Unique products", raw_stats["unique_products"]),
            ("Unique recipe versions", raw_stats["unique_recipe_versions"]),
            ("Unique materials", raw_stats["unique_materials"]),
            ("Unique dosing points", raw_stats["unique_dosing_points"]),
        ]
    )
    lines += ["", "## Normalization outcome", ""]
    lines += _kv_table(
        [
            ("Component rows kept", normalize_stats["component_row_count"]),
            ("Rejected rows", normalize_stats["rejected_row_count"]),
            ("Duplicate rows routed", normalize_stats["duplicate_row_count"]),
            (
                "Percentages kept as null",
                normalize_stats["percentage_parse_failures"],
            ),
        ]
    )
    lines += ["", "## Findings", ""]
    lines += _findings_section(findings)
    lines.append("")
    return "\n".join(lines)


def render_context_report(
    manifest: dict[str, Any],
    orders: pd.DataFrame,
    overlaps: pd.DataFrame,
    gaps: pd.DataFrame,
    transitions: pd.DataFrame,
    coverage: pd.DataFrame,
    events: pd.DataFrame,
) -> str:
    """Production-context narrative: orders, identities, alignment, forensics."""
    lines = ["# BOM Context Report", "", SCOPE_STATEMENT, ""]
    lines += ["## Production context", ""]
    lines += _kv_table(
        [
            ("Orders", manifest["order_count"]),
            ("Products", manifest["product_count"]),
            ("Recipe versions", manifest["recipe_version_count"]),
            ("Distinct BOM signatures", manifest["bom_signature_count"]),
            ("Overlap windows", manifest["overlap_count"]),
            ("Gaps inside coverage", manifest["gap_count"]),
            ("Transitions", len(transitions)),
            (
                "Orders with percentage warnings",
                int(orders["has_percentage_warning"].sum()),
            ),
            (
                "Orders with metadata conflicts",
                int(orders["has_metadata_conflict"].sum()),
            ),
            ("Invalid order windows", int((~orders["is_valid_window"]).sum())),
        ]
    )
    lines += ["", "### Transition types", ""]
    tt = transitions["transition_type"].value_counts() if len(transitions) else {}
    lines += _kv_table([(k, v) for k, v in dict(tt).items()]) or ["_none_"]
    lines += ["", "## Master timeline enrichment", ""]
    lines += _kv_table(
        [
            ("Master rows", manifest["master_timeline_row_count"]),
            ("Timeline rows", manifest["master_timeline_row_count"]),
            ("Exact timestamp alignment", "yes (hard-gated)"),
        ]
    )
    lines += ["", "### Coverage by context status", ""]
    lines += _frame_table(coverage)
    lines += ["", "## Overlap windows", ""]
    lines += _frame_table(overlaps)
    lines += ["", "## Gaps inside BOM coverage", ""]
    lines += _frame_table(gaps)
    lines += ["", "## Forensic candidate-date context (Stage G)", ""]
    lines += _frame_table(
        events[
            [
                "candidate_timestamp",
                "active_order_ids",
                "recipe_versions",
                "nearby_transitions",
                "focus_product_active",
                "context_summary",
            ]
        ]
        if len(events)
        else events
    )
    lines += [
        "",
        "Overlaps and percentage totals are preserved as found; interpreting "
        "them (and any temporal association with anomaly findings) requires "
        "domain review — see the BOM-aware forensic addendum.",
        "",
    ]
    return "\n".join(lines)
