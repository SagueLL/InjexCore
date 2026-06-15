"""Fixtures for the Reference Governance unit tests.

``reference_world`` writes three tiny *completed* upstream runs (sensor-health,
incidents, drift), a synthetic master + behaviour manifest, and a config
pinned to them — so run-level tests drive the real CLI without touching any
real artifact.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.unit.intelligence import c3_world


@pytest.fixture
def reference_world(tmp_path: Path) -> dict[str, Any]:
    master_path, sha = c3_world.write_master(tmp_path)
    behaviour_manifest = c3_world.write_behaviour(tmp_path)
    c3_world.write_sensor_health(tmp_path, sha)
    c3_world.write_incidents(tmp_path)
    c3_world.write_drift(tmp_path, sha)

    config_path = tmp_path / "reference_governance.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "upstream": {
                    "sensor_health_root": (tmp_path / "sensor_health").as_posix(),
                    "sensor_health_run": "latest",
                    "incidents_root": (tmp_path / "incidents").as_posix(),
                    "incidents_run": "latest",
                    "drift_root": (tmp_path / "drift").as_posix(),
                    "drift_run": "latest",
                    "behaviour_manifest": behaviour_manifest.as_posix(),
                    "master_path": master_path.as_posix(),
                },
            }
        ),
        encoding="utf-8",
    )
    out_root = tmp_path / "reference_out"
    return {
        "tmp_path": tmp_path,
        "config_path": config_path,
        "out_root": out_root,
        "master_sha256": sha,
        "args": ["--config", str(config_path), "--output-root", str(out_root)],
    }
