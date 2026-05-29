"""Hybrid column-selection engine shared by the three projection modules.

Each projection module owns its own :class:`SelectorSpec` (loaded from
``configs/specialized_datasets.yaml``) and calls
:func:`select_columns` to resolve it against the master DataFrame.

Selection rules
---------------
1. Start with the union of:
   * columns matching any regex in ``include_patterns``,
   * columns whose semantic category is in ``include_categories``,
   * columns explicitly listed in ``include_columns``.
2. If ``include_metadata`` is true, always preserve ``timestamp``
   (whether it is the index or a column) and every column in
   ``groups.metadata``.
3. Remove any column matching ``exclude_patterns`` or in
   ``exclude_columns``.
4. Deduplicate while preserving the original DataFrame column order.

Findings emitted
----------------
* ``NORMAL`` — one summary per rule (``include_patterns`` /
  ``include_categories`` / ``include_columns`` / ``exclude_*``) recording
  how many columns matched.
* ``AWARE`` — for each name in ``include_columns`` / ``exclude_columns``
  that is not present in the source DataFrame (typo / drift / schema
  change upstream).
* ``IMPORTANT`` — when the resulting projection is empty.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from src.data.datasets.column_groups import ColumnGroups
from src.data.datasets.policy import SelectorSpec
from src.data.datasets.reporting import Finding, Severity


@dataclass(frozen=True)
class SelectionResult:
    """Outcome of applying one :class:`SelectorSpec` to a DataFrame."""

    columns: list[str]
    findings: list[Finding]


def _match_patterns(columns: list[str], patterns: list[str]) -> set[str]:
    if not patterns:
        return set()
    compiled = [re.compile(p) for p in patterns]
    return {c for c in columns for r in compiled if r.search(c)}


def _category_columns(
    columns: list[str], groups: ColumnGroups, categories: list[str],
) -> set[str]:
    if not categories:
        return set()
    wanted = set(categories)
    hits: set[str] = set()
    for col in columns:
        cat = groups.semantic_category(col)
        if cat in wanted:
            hits.add(col)
    return hits


def select_columns(
    df: pd.DataFrame,
    spec: SelectorSpec,
    groups: ColumnGroups,
    *,
    check_name: str,
) -> SelectionResult:
    """Resolve a :class:`SelectorSpec` against ``df``.

    Parameters
    ----------
    df:
        The master DataFrame (or any DataFrame to project from).
    spec:
        The selector configuration for one dataset.
    groups:
        Materialised semantic groups for category-based selection.
    check_name:
        Module name to stamp on every emitted :class:`Finding` (e.g.
        ``"anomaly_detection"``). Allows the orchestrator to group
        findings per dataset in the JSON report.
    """
    columns = list(df.columns)
    findings: list[Finding] = []

    if not spec.enabled:
        findings.append(
            Finding(
                check=check_name,
                severity=Severity.NORMAL,
                finding_type="skipped",
                action_taken="noop",
                evidence={"reason": "disabled"},
            )
        )
        return SelectionResult(columns=[], findings=findings)

    pattern_hits = _match_patterns(columns, spec.include_patterns)
    category_hits = _category_columns(columns, groups, spec.include_categories)

    present_columns = set(columns)
    explicit_present = [c for c in spec.include_columns if c in present_columns]
    explicit_missing = [c for c in spec.include_columns if c not in present_columns]

    selected: set[str] = set()
    selected |= pattern_hits
    selected |= category_hits
    selected |= set(explicit_present)

    if spec.include_metadata:
        meta = set(groups.metadata) & present_columns
        selected |= meta
        if "timestamp" in present_columns:
            selected.add("timestamp")

    exclude_pattern_hits = _match_patterns(columns, spec.exclude_patterns)
    exclude_explicit_present = [
        c for c in spec.exclude_columns if c in present_columns
    ]
    exclude_explicit_missing = [
        c for c in spec.exclude_columns if c not in present_columns
    ]
    selected -= exclude_pattern_hits
    selected -= set(exclude_explicit_present)

    ordered = [c for c in columns if c in selected]

    # --- Findings -----------------------------------------------------------
    if spec.include_patterns:
        findings.append(
            Finding(
                check=check_name,
                severity=Severity.NORMAL,
                finding_type="include_patterns",
                count=len(pattern_hits),
                action_taken=f"match:{len(pattern_hits)}",
                evidence={
                    "patterns": list(spec.include_patterns),
                    "matched": sorted(pattern_hits),
                },
            )
        )
    if spec.include_categories:
        findings.append(
            Finding(
                check=check_name,
                severity=Severity.NORMAL,
                finding_type="include_categories",
                count=len(category_hits),
                action_taken=f"match:{len(category_hits)}",
                evidence={
                    "categories": list(spec.include_categories),
                    "matched": sorted(category_hits),
                },
            )
        )
    if spec.include_columns:
        findings.append(
            Finding(
                check=check_name,
                severity=Severity.NORMAL,
                finding_type="include_columns",
                count=len(explicit_present),
                action_taken=f"match:{len(explicit_present)}",
                evidence={"matched": explicit_present},
            )
        )
        for name in explicit_missing:
            findings.append(
                Finding(
                    check=check_name,
                    severity=Severity.AWARE,
                    finding_type="unmatched_include",
                    column=name,
                    action_taken="skip",
                    evidence={"reason": "column not present in master"},
                )
            )
    if spec.exclude_patterns or spec.exclude_columns:
        findings.append(
            Finding(
                check=check_name,
                severity=Severity.NORMAL,
                finding_type="exclude",
                count=len(exclude_pattern_hits) + len(exclude_explicit_present),
                action_taken=f"drop:{len(exclude_pattern_hits) + len(exclude_explicit_present)}",
                evidence={
                    "patterns": list(spec.exclude_patterns),
                    "explicit": list(spec.exclude_columns),
                    "pattern_matched": sorted(exclude_pattern_hits),
                    "explicit_matched": exclude_explicit_present,
                },
            )
        )
        for name in exclude_explicit_missing:
            findings.append(
                Finding(
                    check=check_name,
                    severity=Severity.AWARE,
                    finding_type="unmatched_exclude",
                    column=name,
                    action_taken="skip",
                    evidence={"reason": "column not present in master"},
                )
            )

    severity = Severity.IMPORTANT if not ordered else Severity.NORMAL
    findings.append(
        Finding(
            check=check_name,
            severity=severity,
            finding_type="projection_summary",
            count=len(ordered),
            action_taken=f"project:{len(ordered)}",
            evidence={
                "source_columns": len(columns),
                "selected_columns": len(ordered),
                "include_metadata": bool(spec.include_metadata),
            },
        )
    )

    return SelectionResult(columns=ordered, findings=findings)


def project(
    df: pd.DataFrame,
    spec: SelectorSpec,
    groups: ColumnGroups,
    *,
    check_name: str,
) -> tuple[pd.DataFrame, list[Finding]]:
    """Convenience wrapper: run :func:`select_columns` and return the
    narrowed DataFrame along with the findings."""
    result = select_columns(df, spec, groups, check_name=check_name)
    if not result.columns:
        # Preserve index so callers can still observe row count / dtype.
        return df.iloc[:, 0:0].copy(), result.findings
    return df[result.columns].copy(), result.findings
