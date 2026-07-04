"""Lineage gate service: projects DashboardChainValidation to the API result."""

from __future__ import annotations

import pytest
from src.api.services import lineage_gate
from src.dashboard.contract import DashboardChainValidation


def _fake_validation(
    severity: str, *, is_valid: bool, canonical: bool
) -> DashboardChainValidation:
    return DashboardChainValidation(
        run_id="r",
        bom_run_id="b",
        is_valid=is_valid,
        severity=severity,
        canonical_match=canonical,
        warnings=["w"],
        component_statuses={},
        lineage_edges=[],
    )


def test_evaluate_lineage_projects_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        lineage_gate,
        "validate_dashboard_chain",
        lambda: _fake_validation("warning", is_valid=True, canonical=True),
    )
    result = lineage_gate.evaluate_lineage()
    assert result.is_valid is True
    assert result.canonical_match is True
    assert result.severity == "warning"
    assert result.warnings == ["w"]


def test_evaluate_lineage_passes_severity_verbatim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        lineage_gate,
        "validate_dashboard_chain",
        lambda: _fake_validation("ok", is_valid=True, canonical=True),
    )
    # Backend "ok" is surfaced verbatim (no mapping to "valid").
    assert lineage_gate.evaluate_lineage().severity == "ok"
