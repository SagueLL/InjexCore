"""CTX-01: operational-context addendum run overrides + fail-closed resolution.

The forensic addendum must be regenerable against the canonical rematerialized
chain via ``--anomaly-run`` / ``--forensic-run``, and must never silently
consume a stale or unresolvable pinned run. These tests drive the resolver and
arg parser directly so they stay fast and free of real-data dependencies.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
from src.context.operational import run_operational_context as roc
from src.context.operational.policy import (
    AddendumPolicy,
    OperationalContextPolicy,
    UpstreamPolicy,
)
from src.context.operational.validation import OperationalContextBlockerError


def _write_run(root: Path, run_id: str, manifest_name: str, component: str) -> Path:
    """Write a tiny *completed* run (manifest last) under ``root/runs/<id>/``."""
    d = root / "runs" / run_id
    d.mkdir(parents=True)
    (d / manifest_name).write_text(
        json.dumps(
            {"component": component, "run_id": run_id, "completion_status": "complete"}
        ),
        encoding="utf-8",
    )
    return d


@pytest.fixture
def world(tmp_path: Path) -> dict[str, object]:
    """Synthetic sensor-health/BOM/anomaly/forensic runs + a pinned policy."""
    sh_root = tmp_path / "sensor_health"
    bom_root = tmp_path / "bom"
    anom_root = tmp_path / "anomaly"
    for_root = tmp_path / "forensics"

    _write_run(sh_root, "sh1", "sensor_health_manifest.json", "sensor_health")
    _write_run(bom_root, "bom1", "bom_context_manifest.json", "bom_context")
    _write_run(anom_root, "anom_pin", "anomaly_fit_manifest.json", "anomaly")
    _write_run(anom_root, "anom_override", "anomaly_fit_manifest.json", "anomaly")
    # The forensic manifest component string is not uniform across writers, so
    # it is resolved without an expected_component check.
    _write_run(for_root, "for_pin", "forensic_manifest.json", "forensics")
    _write_run(for_root, "for_override", "forensic_manifest.json", "forensics")

    policy = OperationalContextPolicy(
        upstream=UpstreamPolicy(
            sensor_health_root=str(sh_root),
            sensor_health_run="sh1",
            bom_root=str(bom_root),
            bom_run="bom1",
            anomaly_root=str(anom_root),
            anomaly_run="anom_pin",
            forensic_root=str(for_root),
            forensic_run="for_pin",
        ),
        forensic_addendum=AddendumPolicy(enabled=True),
    )
    return {"policy": policy}


def _args(**overrides: object) -> argparse.Namespace:
    base = {
        "sensor_health_run": None,
        "bom_run": None,
        "anomaly_run": None,
        "forensic_run": None,
        "skip_addendum": False,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def test_cli_overrides_parsed() -> None:
    args = roc._parse_args(["--anomaly-run", "A", "--forensic-run", "F"])
    assert args.anomaly_run == "A"
    assert args.forensic_run == "F"
    # Defaults stay None so the policy pin wins when no flag is given.
    assert roc._parse_args([]).anomaly_run is None
    assert roc._parse_args([]).forensic_run is None


def test_config_pin_used_when_no_override(world: dict[str, object]) -> None:
    _, _, anomaly_dir, forensic_dir = roc._resolve_upstream_dirs(
        world["policy"], _args()
    )
    assert anomaly_dir is not None and anomaly_dir.name == "anom_pin"
    assert forensic_dir is not None and forensic_dir.name == "for_pin"


def test_override_beats_config_pin(world: dict[str, object]) -> None:
    _, _, anomaly_dir, forensic_dir = roc._resolve_upstream_dirs(
        world["policy"], _args(anomaly_run="anom_override", forensic_run="for_override")
    )
    assert anomaly_dir is not None and anomaly_dir.name == "anom_override"
    assert forensic_dir is not None and forensic_dir.name == "for_override"


def test_skip_addendum_requires_no_override(world: dict[str, object]) -> None:
    # No anomaly/forensic override and a (here valid) pin: skipping must not
    # resolve them at all — addendum dirs come back None.
    sh_dir, bom_dir, anomaly_dir, forensic_dir = roc._resolve_upstream_dirs(
        world["policy"], _args(skip_addendum=True)
    )
    assert sh_dir.name == "sh1" and bom_dir.name == "bom1"
    assert anomaly_dir is None and forensic_dir is None


def test_stale_config_pin_fails_closed(world: dict[str, object]) -> None:
    policy: OperationalContextPolicy = world["policy"]  # type: ignore[assignment]
    policy.upstream.anomaly_run = "does-not-exist"
    with pytest.raises(OperationalContextBlockerError) as exc:
        roc._resolve_upstream_dirs(policy, _args())
    assert "--anomaly-run" in str(exc.value)
    assert "does-not-exist" in str(exc.value)


def test_valid_override_selects_addendum_path(world: dict[str, object]) -> None:
    # A pin that is stale is rescued by a valid override — the addendum path is
    # selected (both dirs resolved) instead of failing closed.
    policy: OperationalContextPolicy = world["policy"]  # type: ignore[assignment]
    policy.upstream.anomaly_run = "does-not-exist"
    _, _, anomaly_dir, forensic_dir = roc._resolve_upstream_dirs(
        policy, _args(anomaly_run="anom_override")
    )
    assert anomaly_dir is not None and anomaly_dir.name == "anom_override"
    assert forensic_dir is not None and forensic_dir.name == "for_pin"
