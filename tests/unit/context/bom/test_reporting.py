"""Report renderers produce the required sections and scope statement."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd
from src.context.bom import aggregate, normalize, reporting, timeline, validation
from src.context.bom.policy import BomContextPolicy


def _pipeline_pieces(
    raw_bom_factory: Callable[..., pd.DataFrame],
    master_ts_factory: Callable[..., pd.DatetimeIndex],
    policy: BomContextPolicy,
) -> dict:
    raw = raw_bom_factory([{}, {"order_id": "101", "percentage": "39,5"}])
    raw_stats, findings = validation.assess_raw_quality(raw, policy)
    norm = normalize.normalize(raw, policy)
    orders, _ = aggregate.aggregate_orders(norm.components, policy)
    overlaps = aggregate.detect_overlaps(orders)
    orders = aggregate.attach_overlaps(orders, overlaps)
    gaps = aggregate.detect_gaps(orders, 0.0)
    transitions = aggregate.classify_transitions(orders, 0.0)
    tl, _ = timeline.build_context_timeline(orders, master_ts_factory())
    events = timeline.event_windows(
        orders,
        transitions,
        overlaps,
        gaps,
        norm.components,
        policy.forensic_windows.model_copy(update={"candidate_dates": ["2024-09-01"]}),
    )
    return {
        "raw_stats": raw_stats,
        "norm": norm,
        "orders": orders,
        "overlaps": overlaps,
        "gaps": gaps,
        "transitions": transitions,
        "coverage": aggregate.coverage_summary(tl),
        "events": events,
        "findings": findings,
    }


def test_quality_report_sections(
    raw_bom_factory: Callable[..., pd.DataFrame],
    master_ts_factory: Callable[..., pd.DatetimeIndex],
    bom_policy: BomContextPolicy,
) -> None:
    p = _pipeline_pieces(raw_bom_factory, master_ts_factory, bom_policy)
    text = reporting.render_quality_report(
        p["raw_stats"], p["norm"].stats, p["findings"]
    )
    assert reporting.SCOPE_STATEMENT in text
    for heading in (
        "## Source parsing",
        "## Missingness by column",
        "## Integrity",
        "## Cardinality",
        "## Normalization outcome",
        "## Findings",
    ):
        assert heading in text


def test_context_report_sections(
    raw_bom_factory: Callable[..., pd.DataFrame],
    master_ts_factory: Callable[..., pd.DatetimeIndex],
    bom_policy: BomContextPolicy,
) -> None:
    p = _pipeline_pieces(raw_bom_factory, master_ts_factory, bom_policy)
    manifest = {
        "order_count": len(p["orders"]),
        "product_count": 1,
        "recipe_version_count": 1,
        "bom_signature_count": 2,
        "overlap_count": len(p["overlaps"]),
        "gap_count": len(p["gaps"]),
        "master_timeline_row_count": 96,
    }
    text = reporting.render_context_report(
        manifest,
        p["orders"],
        p["overlaps"],
        p["gaps"],
        p["transitions"],
        p["coverage"],
        p["events"],
    )
    assert reporting.SCOPE_STATEMENT in text
    for heading in (
        "## Production context",
        "## Master timeline enrichment",
        "### Coverage by context status",
        "## Forensic candidate-date context",
    ):
        assert heading in text
    assert "matched_single_order" in text
