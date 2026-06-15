"""Reference registry construction.

Every run deterministically re-seeds the registry from the behaviour fit
manifest — there is no hidden cross-run state. Row 0 is always the immutable
baseline ``reference_v1`` (the original leakage-safe train window); candidate
references, when proposed, are appended by :mod:`proposals`. The registry is
a record of *what exists and its status*, never an instruction to change it.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

REGISTRY_COLUMNS = [
    "reference_id",
    "reference_type",
    "status",
    "created_at",
    "source_train_start",
    "source_train_end",
    "dataset_sha256",
    "sensor_scope",
    "profile_scope",
    "context_scope",
    "excluded_sensors",
    "source_artifacts",
    "reason",
    "notes",
]

REFERENCE_V1_ID = "reference_v1"


def build_registry(
    behaviour_manifest: dict[str, Any],
    master_sha256: str,
    behaviour_manifest_path: str,
) -> pd.DataFrame:
    """Seed the registry with the immutable ``reference_v1`` baseline row."""
    fit_window = behaviour_manifest.get("fit_window", {})
    sensors = behaviour_manifest.get("sensors", [])
    sensor_scope = (
        f"all_supported_sensors({len(sensors)})" if sensors else "all_supported_sensors"
    )
    row: dict[str, Any] = {
        "reference_id": REFERENCE_V1_ID,
        "reference_type": "baseline",
        "status": "current",
        "created_at": str(behaviour_manifest.get("fit_timestamp", "")),
        "source_train_start": str(fit_window.get("train_start", "")),
        "source_train_end": str(fit_window.get("train_end", "")),
        "dataset_sha256": master_sha256,
        "sensor_scope": sensor_scope,
        "profile_scope": "all_profiles",
        "context_scope": "none",
        "excluded_sensors": "",
        "source_artifacts": behaviour_manifest_path,
        "reason": "original leakage-safe train reference",
        "notes": (
            "Baseline reference; immutable. Predates the inlet_hopper_points "
            "instrumentation fault confirmed from 2024-09-17."
        ),
    }
    return pd.DataFrame([row], columns=REGISTRY_COLUMNS)
