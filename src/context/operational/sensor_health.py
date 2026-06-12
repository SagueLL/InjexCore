"""Sensor-health context consumption for the overlay.

Reads a *completed* Sensor Health run's per-timestamp quality timeline and
exposes the four overlay columns. Evidence lists are preserved untouched —
the overlay never collapses which sensors are faulty/warning into a bare
flag.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.context.operational.io import SENSOR_HEALTH_MANIFEST

#: Columns the overlay takes from the sensor-health quality timeline.
HEALTH_COLUMNS = [
    "sensor_health_context",
    "faulty_sensors",
    "warning_sensors",
    "quarantine_recommended_sensors",
]

HEALTH_CONTEXTS = ("all_sensors_healthy", "sensor_warning", "sensor_faulty", "unknown")


def load_sensor_quality_timeline(
    run_path: Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Quality timeline + manifest of a completed sensor-health run."""
    timeline = pd.read_parquet(
        run_path / "summaries" / "sensor_quality_timeline.parquet"
    )
    timeline["timestamp"] = pd.to_datetime(timeline["timestamp"], errors="raise")
    missing = [c for c in HEALTH_COLUMNS if c not in timeline.columns]
    if missing:
        raise ValueError(
            f"Sensor quality timeline at {run_path} is missing columns {missing}"
        )
    manifest = json.loads(
        (run_path / SENSOR_HEALTH_MANIFEST).read_text(encoding="utf-8")
    )
    return timeline, manifest
