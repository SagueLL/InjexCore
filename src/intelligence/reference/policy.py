"""Pydantic policy schema for Reference Governance.

Materialised from ``configs/reference_governance.yaml``. The proposal and
reference status vocabularies are the contract (closed sets); the upstream
pins, the quarantine candidate allow-list and the candidate-v2 materiality
thresholds are tunables. Every model inherits :class:`StrictModel` — a
misspelled YAML key raises instead of being silently dropped.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import Field

from src.preprocessing._common.models import StrictModel

#: Closed vocabularies (the contract, not tunables).
PROPOSAL_STATUSES = (
    "candidate",
    "pending_review",
    "approved",
    "rejected",
    "deprecated",
)
REFERENCE_STATUSES = (
    "current",
    "candidate",
    "pending_review",
    "approved",
    "rejected",
    "deprecated",
)
REVIEW_STATUSES = ("pending_review", "confirmed", "dismissed", "resolved")


class ReferenceUpstreamPolicy(StrictModel):
    """Upstream run roots + pins (completed-run resolution; ``latest`` ok)."""

    sensor_health_root: str = "data/intelligence/sensor_health"
    sensor_health_run: str = "latest"
    incidents_root: str = "data/intelligence/incidents"
    incidents_run: str = "latest"
    drift_root: str = "data/intelligence/drift"
    drift_run: str = "latest"
    behaviour_manifest: str = "data/intelligence/behaviour/behaviour_fit_manifest.json"
    master_path: str = "data/datasets/master/master_dataset.parquet"


class QuarantinePolicy(StrictModel):
    """Allow-list of sensors eligible for a quarantine *proposal*.

    A proposal is only ever created when upstream sensor-health evidence
    actually recommends quarantine for the sensor; this list narrows that
    set further (empty == accept every recommended sensor). It never
    approves or applies anything.
    """

    candidate_sensors: list[str] = Field(
        default_factory=lambda: ["inlet_hopper_points"]
    )


class CandidateV2Policy(StrictModel):
    """When residual healthy-only drift counts as *materially significant*.

    Residual is material only when both gates pass: at least
    ``residual_window_min`` sensor windows still flag drift after
    faulty/quarantined-sensor evidence is excluded, AND those windows are at
    least ``residual_fraction_min`` of all sensor windows. Conservative by
    design — a candidate Reference v2 is proposed but never auto-approved.
    """

    residual_window_min: int = Field(50, ge=0)
    residual_fraction_min: float = Field(0.05, ge=0.0, le=1.0)


class ReferencePolicy(StrictModel):
    """Aggregate policy loaded from ``configs/reference_governance.yaml``."""

    upstream: ReferenceUpstreamPolicy = Field(default_factory=ReferenceUpstreamPolicy)
    quarantine: QuarantinePolicy = Field(default_factory=QuarantinePolicy)
    candidate_v2: CandidateV2Policy = Field(default_factory=CandidateV2Policy)
    output_root: str = "data/intelligence/reference"


def load_policy(yaml_path: Path) -> ReferencePolicy:
    """Read the YAML config and validate it against the schema."""
    if not yaml_path.exists():
        raise FileNotFoundError(f"Reference governance policy not found at {yaml_path}")
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    return ReferencePolicy.model_validate(raw)
