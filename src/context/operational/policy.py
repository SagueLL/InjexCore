"""Pydantic policy schema for the Operational Context Overlay.

Materialised from ``configs/operational_context.yaml``. Every model inherits
:class:`StrictModel` — a misspelled YAML key raises. Steam thresholds and
persistence windows are tunables; the context vocabularies and the overlay
schema are the contract and stay hardcoded in the stage modules.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import Field

from src.preprocessing._common.models import StrictModel


class TimelinePolicy(StrictModel):
    master_path: str = "data/datasets/master/master_dataset.parquet"
    expected_master_rows: int | None = 167331  # hard gate; null disables


class UpstreamPolicy(StrictModel):
    """Upstream artifact locations + run pins.

    Behaviour artifacts are fixed paths (Iteration A is not run-versioned);
    sensor-health / BOM / anomaly / forensic are run-versioned and resolved
    via the completed-run convention (``latest`` supported).
    """

    # Empty -> resolve the latest completed behaviour run (run-versioned cutover).
    # Set an explicit path only to pin a specific behaviour artifact (tests).
    profile_labels_path: str = ""
    behaviour_manifest_path: str = ""
    sensor_health_root: str = "data/intelligence/sensor_health"
    sensor_health_run: str = "latest"
    bom_root: str = "data/context/bom"
    bom_run: str = "20260612T124909Z"  # pinned: reproducibility over convenience
    anomaly_root: str = "data/intelligence/anomaly"
    anomaly_run: str = "20260611T173316Z"  # addendum only
    forensic_root: str = "data/intelligence/forensics"
    forensic_run: str = "20260612T101850Z"  # addendum only


class SteamPolicy(StrictModel):
    """Steam-conditioning context derivation (profile-independent).

    Thresholds sit in the wide dead band between regimes (stopped medians
    ~0.18 bar / 34 °C vs running ~2.5–2.9 bar / 85–89 °C). Classification is
    never single-row: a centered persistence window decides.
    """

    pressure_sensor: str = "steam_valve_pressure_me2"
    temp_sensor: str = "conditioner_steam_loop_temp"
    auxiliary_sensors: list[str] = Field(
        default_factory=lambda: ["steam_valve_temp_me2"]
    )
    pressure_active_threshold: float = 1.0  # bar
    temp_active_threshold: float = 60.0  # degC
    window_rows: int = Field(241, ge=3)  # centered, ~±2 h at 1-min cadence
    min_valid_rows: int = Field(30, ge=1)
    on_fraction: float = Field(0.9, gt=0.5, le=1.0)
    off_fraction: float = Field(0.1, ge=0.0, lt=0.5)


class ContextKeyPolicy(StrictModel):
    """Deterministic composite key — metadata only, never a model input."""

    enabled: bool = True
    fields: list[str] = Field(
        default_factory=lambda: [
            "profile",
            "steam_context",
            "sensor_health_context",
            "bom_context_status",
        ]
    )


class TransitionsPolicy(StrictModel):
    track_profile: bool = True
    track_steam: bool = True
    track_sensor_health: bool = True
    track_product: bool = True
    track_recipe: bool = True
    track_bom_overlap: bool = True
    track_bom_gap: bool = True


class AddendumPolicy(StrictModel):
    enabled: bool = True
    output_root: str = "data/intelligence/forensics/context_addenda"
    candidate_dates: list[str] = Field(
        default_factory=lambda: [
            "2024-09-09",
            "2024-09-12",
            "2024-09-13",
            "2024-09-16",
            "2024-09-18",
        ]
    )
    window_hours: int = Field(24, ge=1)


class OperationalContextPolicy(StrictModel):
    """Aggregate policy loaded from ``configs/operational_context.yaml``."""

    timeline: TimelinePolicy = Field(default_factory=TimelinePolicy)
    upstream: UpstreamPolicy = Field(default_factory=UpstreamPolicy)
    steam: SteamPolicy = Field(default_factory=SteamPolicy)
    context_key: ContextKeyPolicy = Field(default_factory=ContextKeyPolicy)
    transitions: TransitionsPolicy = Field(default_factory=TransitionsPolicy)
    forensic_addendum: AddendumPolicy = Field(default_factory=AddendumPolicy)


def load_policy(yaml_path: Path) -> OperationalContextPolicy:
    """Read the YAML config and validate it against the schema."""
    if not yaml_path.exists():
        raise FileNotFoundError(f"Operational-context policy not found at {yaml_path}")
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    return OperationalContextPolicy.model_validate(raw)
