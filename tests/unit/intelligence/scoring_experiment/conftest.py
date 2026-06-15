"""Fixtures for the Controlled Scoring Experiment unit tests.

``scoring_world`` writes six tiny *completed* upstream runs (anomaly,
sensor-health, drift, incidents, operational context, and a pre-baked
reference governance run), a synthetic master, and a config pinned to them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.unit.intelligence import c3_world


@pytest.fixture
def scoring_world(tmp_path: Path) -> dict[str, Any]:
    master_path, sha = c3_world.write_master(tmp_path)
    c3_world.write_anomaly(tmp_path, sha)
    c3_world.write_sensor_health(tmp_path, sha)
    c3_world.write_drift(tmp_path, sha)
    c3_world.write_incidents(tmp_path)
    c3_world.write_operational(tmp_path, sha)
    c3_world.write_reference_run(tmp_path, sha)

    config_path = tmp_path / "scoring_experiment.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "upstream": {
                    "anomaly_root": (tmp_path / "anomaly").as_posix(),
                    "anomaly_run": "latest",
                    "sensor_health_root": (tmp_path / "sensor_health").as_posix(),
                    "sensor_health_run": "latest",
                    "drift_root": (tmp_path / "drift").as_posix(),
                    "drift_run": "latest",
                    "incidents_root": (tmp_path / "incidents").as_posix(),
                    "incidents_run": "latest",
                    "operational_root": (tmp_path / "operational").as_posix(),
                    "operational_run": "latest",
                    "reference_root": (tmp_path / "reference").as_posix(),
                    "reference_run": "latest",
                    "master_path": master_path.as_posix(),
                }
            }
        ),
        encoding="utf-8",
    )
    out_root = tmp_path / "scoring_out"
    decision_root = tmp_path / "reference_decision"
    return {
        "tmp_path": tmp_path,
        "sha": sha,
        "config_path": config_path,
        "out_root": out_root,
        "decision_root": decision_root,
        "args": [
            "--config",
            str(config_path),
            "--output-root",
            str(out_root),
            "--decision-root",
            str(decision_root),
        ],
    }
