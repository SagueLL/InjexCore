"""Pydantic policy schema for the Incident Aggregation component.

Materialised from ``configs/incidents_intelligence.yaml``. The incident
taxonomies (type, status, severity, review status, relationship types) are
the contract and live here as closed vocabularies; grouping gaps, burst
thresholds and review-pack sizing are tunables. Every model inherits
:class:`StrictModel` — a misspelled YAML key raises.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import Field

from src.preprocessing._common.models import StrictModel

#: Closed vocabularies (the contract, not tunables).
INCIDENT_TYPES = (
    "sensor_fault",
    "sensor_warning",
    "process_drift",
    "context_shift",
    "anomaly_burst",
    "correlation_break",
    "multivariate_shift",
    "data_quality_issue",
    "unknown",
)
INCIDENT_STATUSES = ("open", "persistent", "resolved", "dismissed", "pending_review")
INCIDENT_SEVERITIES = ("info", "warning", "anomaly", "critical")
REVIEW_STATUSES = ("pending_review", "confirmed", "dismissed", "resolved")
RELATIONSHIP_TYPES = (
    "temporally_adjacent",
    "overlaps",
    "contains",
    "possibly_explains",
    "corroborates",
    "shares_sensors",
    "shares_context",
    "follows",
    "unknown",
)

#: Mapping from drift-event types to incident types.
DRIFT_TYPE_TO_INCIDENT = {
    "sensor_drift": "sensor_fault",
    "process_drift": "process_drift",
    "context_shift": "context_shift",
    "profile_composition_shift": "context_shift",
    "correlation_shift": "correlation_break",
    "multivariate_shift": "multivariate_shift",
    "unknown_shift": "unknown",
}


class IncidentsUpstreamPolicy(StrictModel):
    """Upstream run roots + pins (completed-run resolution; ``latest`` ok)."""

    drift_root: str = "data/intelligence/drift"
    drift_run: str = "latest"
    sensor_health_root: str = "data/intelligence/sensor_health"
    sensor_health_run: str = "latest"
    anomaly_root: str = "data/intelligence/anomaly"
    anomaly_run: str = "latest"
    operational_root: str = "data/context/operational"
    operational_run: str = "latest"
    bom_root: str = "data/context/bom"
    bom_run: str = "latest"


class BurstPolicy(StrictModel):
    """Row-level anomaly severities -> sustained anomaly-burst candidates."""

    enabled: bool = True
    bucket_freq: str = "15min"
    rate_threshold: float = Field(0.5, gt=0.0, le=1.0)
    min_duration_minutes: int = Field(60, ge=1)
    gap_merge_buckets: int = Field(1, ge=0)


class GroupingPolicy(StrictModel):
    """Temporal-adjacency gaps per candidate family + affected-set gate."""

    sensor_health_max_gap_minutes: int = Field(240, ge=0)
    drift_max_gap_minutes: int = Field(1440, ge=0)
    burst_max_gap_minutes: int = Field(60, ge=0)
    context_max_gap_minutes: int = Field(240, ge=0)
    affected_jaccard: float = Field(0.5, ge=0.0, le=1.0)
    #: When one (type, family) still yields more incidents than this, the
    #: pattern is recurring routine behaviour — collapsed into ONE reviewable
    #: incident (recorded transparently), not dozens of rows. Applied only to
    #: the routine-pattern types below: bursts and faults are never collapsed.
    recurring_collapse_min: int = Field(10, ge=2)
    recurring_collapse_types: list[str] = Field(
        default_factory=lambda: [
            "sensor_warning",
            "context_shift",
            "data_quality_issue",
        ]
    )
    #: Same-type incidents on exactly the same sensors whose intervals
    #: overlap by at least this fraction merge across sources (a drift-
    #: promoted event and its sensor-health original are one episode).
    cross_source_overlap_fraction: float = Field(0.7, gt=0.0, le=1.0)
    context_transition_types: list[str] = Field(
        default_factory=lambda: ["steam_context_change", "sensor_health_change"]
    )


class SuppressionPolicy(StrictModel):
    """Bursts already explained by a stronger sensor-fault incident."""

    enabled: bool = True
    coverage_fraction: float = Field(0.7, gt=0.0, le=1.0)
    require_shared_sensors: bool = True


class RelationshipsPolicy(StrictModel):
    adjacency_minutes: int = Field(360, ge=0)
    follows_max_minutes: int = Field(1440, ge=0)
    min_confidence: float = Field(0.2, ge=0.0, le=1.0)


def _default_actions() -> dict[str, list[str]]:
    return {
        "sensor_fault": ["inspect_sensor_channel"],
        "sensor_warning": ["inspect_sensor_channel"],
        "data_quality_issue": ["review_historian_mapping"],
        "process_drift": [
            "review_maintenance_log",
            "review_setpoint_changes",
            "compare_healthy_only_drift",
        ],
        "context_shift": ["review_setpoint_changes", "review_operator_notes"],
        "anomaly_burst": ["review_maintenance_log"],
        "correlation_break": ["compare_healthy_only_drift"],
        "multivariate_shift": [
            "compare_healthy_only_drift",
            "inspect_product_recipe_context",
        ],
        "unknown": ["review_operator_notes"],
    }


class ActionsPolicy(StrictModel):
    """Per-incident-type recommended actions (quarantine flags hardcoded)."""

    by_type: dict[str, list[str]] = Field(default_factory=_default_actions)
    quarantine_for_persistent_critical_sensor_fault: bool = True
    counter_reset_action: str = "inspect_counter_reset"


class ReviewPackPolicy(StrictModel):
    max_rows: int = Field(200, ge=1)
    dedup_overlap_fraction: float = Field(0.8, gt=0.0, le=1.0)


class AddendumPolicy(StrictModel):
    """Drift-aware forensic addendum (read-only; never mutates upstream)."""

    enabled: bool = True
    output_root: str = "data/intelligence/forensics/drift_addenda"
    top_events: int = Field(15, ge=1)


class IncidentsPolicy(StrictModel):
    """Aggregate policy loaded from ``configs/incidents_intelligence.yaml``."""

    upstream: IncidentsUpstreamPolicy = Field(default_factory=IncidentsUpstreamPolicy)
    bursts: BurstPolicy = Field(default_factory=BurstPolicy)
    grouping: GroupingPolicy = Field(default_factory=GroupingPolicy)
    suppression: SuppressionPolicy = Field(default_factory=SuppressionPolicy)
    relationships: RelationshipsPolicy = Field(default_factory=RelationshipsPolicy)
    actions: ActionsPolicy = Field(default_factory=ActionsPolicy)
    review_pack: ReviewPackPolicy = Field(default_factory=ReviewPackPolicy)
    forensic_addendum: AddendumPolicy = Field(default_factory=AddendumPolicy)


def load_policy(yaml_path: Path) -> IncidentsPolicy:
    """Read the YAML config and validate it against the schema."""
    if not yaml_path.exists():
        raise FileNotFoundError(f"Incidents policy not found at {yaml_path}")
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    return IncidentsPolicy.model_validate(raw)
