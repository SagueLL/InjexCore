"""Pydantic policy schema for the Controlled Scoring Experiment.

Materialised from ``configs/scoring_experiment.yaml``. The scenario ids are
the contract; upstream pins, the top-N report sizing and the decision-report
toggle are tunables. Every model inherits :class:`StrictModel`.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import Field

from src.preprocessing._common.models import StrictModel

#: Static scenario ids. The quarantine scenario id is derived at runtime from
#: the pending proposal sensor(s) — ``quarantine_<sensor>_interpretive`` for a
#: single target or ``quarantine_proposals_interpretive`` for several (GOV-02).
STATIC_SCENARIO_IDS = (
    "baseline_v1",
    "healthy_only_proxy",
    "candidate_reference_needed",
)


class ScoringUpstreamPolicy(StrictModel):
    """Upstream run roots + pins (completed-run resolution; ``latest`` ok)."""

    anomaly_root: str = "data/intelligence/anomaly"
    anomaly_run: str = "latest"
    sensor_health_root: str = "data/intelligence/sensor_health"
    sensor_health_run: str = "latest"
    drift_root: str = "data/intelligence/drift"
    drift_run: str = "latest"
    incidents_root: str = "data/intelligence/incidents"
    incidents_run: str = "latest"
    operational_root: str = "data/context/operational"
    operational_run: str = "latest"
    reference_root: str = "data/intelligence/reference"
    reference_run: str = "latest"
    master_path: str = "data/datasets/master/master_dataset.parquet"


class ReportingPolicy(StrictModel):
    """How many rows to surface in the human-facing summaries."""

    top_remaining: int = Field(10, ge=1)


class DecisionReportPolicy(StrictModel):
    """The read-only decision-report forensic addendum."""

    enabled: bool = True
    output_root: str = "data/intelligence/forensics/reference_decision"


class ScoringPolicy(StrictModel):
    """Aggregate policy loaded from ``configs/scoring_experiment.yaml``."""

    upstream: ScoringUpstreamPolicy = Field(default_factory=ScoringUpstreamPolicy)
    reporting: ReportingPolicy = Field(default_factory=ReportingPolicy)
    decision_report: DecisionReportPolicy = Field(default_factory=DecisionReportPolicy)
    output_root: str = "data/intelligence/scoring_experiments"


def load_policy(yaml_path: Path) -> ScoringPolicy:
    """Read the YAML config and validate it against the schema."""
    if not yaml_path.exists():
        raise FileNotFoundError(f"Scoring experiment policy not found at {yaml_path}")
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    return ScoringPolicy.model_validate(raw)
