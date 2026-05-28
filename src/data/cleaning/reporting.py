"""Finding dataclass and report writers shared by every cleaning module.

The same :class:`Finding` shape is emitted by every detect/apply step; the
JSON writer dumps the full structured list, the Markdown writer groups by
severity for human review.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable


class Severity(str, Enum):
    CRITICAL = "critical"
    IMPORTANT = "important"
    AWARE = "aware"
    NORMAL = "normal"


_SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.IMPORTANT: 1,
    Severity.AWARE: 2,
    Severity.NORMAL: 3,
}


@dataclass
class Finding:
    """A single anomaly surfaced by a cleaning module.

    Attributes
    ----------
    check:
        Module name that produced the finding (e.g. ``"missing_values"``).
    severity:
        One of :class:`Severity`.
    finding_type:
        Subtype within the check (e.g. ``"broken_sensor"``, ``"frozen_run"``).
    column:
        Affected column, or ``None`` when the finding is row-level only.
    row_range:
        Inclusive ``(start, end)`` integer row indices, or ``None``.
    count:
        Number of cells/rows involved. Defaults to ``1``.
    action_taken:
        Free-form remediation summary (``"drop"``, ``"forward_fill"``,
        ``"clip"``, ``"tag_only"``, ``"none"`` ...).
    evidence:
        Optional dictionary with arbitrary debug payload (sample values,
        timestamps, thresholds, etc.). Kept JSON-serialisable.
    """

    check: str
    severity: Severity
    finding_type: str
    column: str | None = None
    row_range: tuple[int, int] | None = None
    count: int = 1
    action_taken: str = "none"
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["severity"] = self.severity.value
        if self.row_range is not None:
            d["row_range"] = list(self.row_range)
        return d


_MAX_LIST_EVIDENCE = 20  # truncate per-finding list fields beyond this length


def _truncate_evidence(d: dict[str, Any]) -> dict[str, Any]:
    """Replace long list-valued evidence fields with a head/tail sample."""
    out: dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, list) and len(v) > _MAX_LIST_EVIDENCE:
            half = _MAX_LIST_EVIDENCE // 2
            out[k] = v[:half] + ["..."] + v[-half:]
            out[f"{k}_total"] = len(v)
        else:
            out[k] = v
    return out


def write_json(findings: Iterable[Finding], path: Path) -> None:
    """Write the full finding list as JSON, grouped by check.

    Long list-valued evidence fields (e.g. row indices) are truncated to
    a head/tail sample to keep the report human-readable. The full lists
    remain on the in-memory ``Finding`` objects for the apply step.
    """
    by_check: dict[str, list[dict[str, Any]]] = defaultdict(list)
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for f in findings:
        d = f.to_dict()
        if d.get("evidence"):
            d["evidence"] = _truncate_evidence(d["evidence"])
        by_check[f.check].append(d)
        counts[f.check][f.severity.value] += 1

    payload = {
        "summary": {
            check: dict(sev_counts) for check, sev_counts in counts.items()
        },
        "findings_by_check": dict(by_check),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def write_markdown(
    findings: Iterable[Finding],
    path: Path,
    title: str = "Cleaning Report",
) -> None:
    """Write a human-readable Markdown report, grouped by severity."""
    findings_list = list(findings)
    by_severity: dict[Severity, list[Finding]] = defaultdict(list)
    for f in findings_list:
        by_severity[f.severity].append(f)

    lines: list[str] = [f"# {title}", ""]
    lines.append(f"**Total findings:** {len(findings_list)}")
    lines.append("")
    lines.append("| Severity | Count |")
    lines.append("|----------|-------|")
    for sev in sorted(by_severity, key=lambda s: _SEVERITY_ORDER[s]):
        lines.append(f"| {sev.value} | {len(by_severity[sev])} |")
    lines.append("")

    for sev in sorted(by_severity, key=lambda s: _SEVERITY_ORDER[s]):
        bucket = by_severity[sev]
        lines.append(f"## {sev.value.upper()} ({len(bucket)})")
        lines.append("")
        lines.append("| Check | Type | Column | Rows | Count | Action |")
        lines.append("|-------|------|--------|------|-------|--------|")
        for f in bucket:
            rr = (
                f"{f.row_range[0]}–{f.row_range[1]}"
                if f.row_range is not None
                else "-"
            )
            col = f.column or "-"
            lines.append(
                f"| {f.check} | {f.finding_type} | {col} | {rr} | "
                f"{f.count} | {f.action_taken} |"
            )
        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
