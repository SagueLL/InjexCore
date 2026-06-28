"""Orchestrator CLI — --no-write, manifest-last, immutability."""

from __future__ import annotations

import argparse
import json
import types
from collections.abc import Callable
from pathlib import Path

import pandas as pd
import pytest
from src.context.bom import io, run_bom_context
from src.context.bom.policy import ForensicAddendumPolicy
from src.context.bom.validation import BomContextBlockerError

_CONFIG_YAML = """
timeline:
  expected_master_rows: null
forensic_addendum:
  enabled: false
"""


@pytest.fixture
def cli_env(
    tmp_path: Path,
    raw_bom_factory: Callable[..., pd.DataFrame],
    master_ts_factory: Callable[..., pd.DatetimeIndex],
) -> dict:
    """Config + CSV + master parquet + output root, all under tmp_path."""
    config = tmp_path / "bom.yaml"
    config.write_text(_CONFIG_YAML, encoding="utf-8")

    csv_path = tmp_path / "bom.csv"
    frame = raw_bom_factory(
        [
            {},
            {"material_code": "1901", "percentage": "39,5"},
            {
                "order_id": "101",
                "start_timestamp": "2024-09-02 00:00:00",
                "end_timestamp": "2024-09-03 00:00:00",
                "recipe_version": "v2",
            },
        ]
    )
    frame.drop(columns=["source_row_number", "source_file"]).to_csv(
        csv_path, index=False, encoding="utf-8-sig"
    )

    master_path = tmp_path / "master.parquet"
    pd.DataFrame({"timestamp": master_ts_factory(periods=96)}).to_parquet(
        master_path, index=False
    )

    out_root = tmp_path / "bom_out"
    return {
        "args": [
            "--config",
            str(config),
            "--csv",
            str(csv_path),
            "--master",
            str(master_path),
            "--output-root",
            str(out_root),
        ],
        "csv": csv_path,
        "master": master_path,
        "out_root": out_root,
    }


def test_no_write_leaves_output_untouched(cli_env: dict) -> None:
    assert run_bom_context.main([*cli_env["args"], "--no-write"]) == 0
    assert not cli_env["out_root"].exists()


def test_full_run_writes_complete_resolvable_manifest(cli_env: dict) -> None:
    sha_before = io.file_sha256(cli_env["csv"])
    assert run_bom_context.main([*cli_env["args"], "--run-id", "t1"]) == 0

    out = cli_env["out_root"] / "runs" / "t1"
    manifest = json.loads((out / io.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["completion_status"] == "complete"
    assert manifest["run_id"] == "t1"
    assert manifest["raw_row_count"] == 3
    assert manifest["order_count"] == 2
    assert manifest["addendum"] == "skipped"
    assert manifest["source_sha256"] == sha_before

    # Manifest presence marks the run resolvable.
    assert io.resolve_run(cli_env["out_root"], "latest", io.MANIFEST_NAME) == out
    timeline = pd.read_parquet(out / io.TIMELINE_FILE)
    assert len(timeline) == 96
    for rel in (io.COMPONENTS_FILE, io.ORDERS_FILE, io.COVERAGE_FILE):
        assert (out / rel).exists()
    assert (out / io.QUALITY_REPORT_MD).exists()
    assert (out / io.CONTEXT_REPORT_MD).exists()

    # Inputs untouched.
    assert io.file_sha256(cli_env["csv"]) == sha_before


def test_manifest_written_last_failed_run_not_resolvable(
    cli_env: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = io.write_table

    def explode(frame: pd.DataFrame, path: Path) -> None:
        if path.name == io.TIMELINE_FILE.name:
            raise OSError("disk full")
        original(frame, path)

    monkeypatch.setattr(io, "write_table", explode)
    with pytest.raises(OSError, match="disk full"):
        run_bom_context.main([*cli_env["args"], "--run-id", "crashed"])

    run_dir = cli_env["out_root"] / "runs" / "crashed"
    assert run_dir.exists()  # partial artifacts may exist...
    assert not (run_dir / io.MANIFEST_NAME).exists()  # ...but no manifest
    with pytest.raises(FileNotFoundError):
        io.resolve_run(cli_env["out_root"], "latest", io.MANIFEST_NAME)


def test_expected_rows_gate_blocks_mismatched_master(
    cli_env: dict, tmp_path: Path
) -> None:
    strict = tmp_path / "strict.yaml"
    strict.write_text(_CONFIG_YAML.replace("null", "12345"), encoding="utf-8")
    args = list(cli_env["args"])
    args[args.index("--config") + 1] = str(strict)

    with pytest.raises(BomContextBlockerError, match="12345"):
        run_bom_context.main([*args, "--no-write"])


def test_deterministic_outputs_across_runs(cli_env: dict) -> None:
    assert run_bom_context.main([*cli_env["args"], "--run-id", "a"]) == 0
    assert run_bom_context.main([*cli_env["args"], "--run-id", "b"]) == 0
    root = cli_env["out_root"] / "runs"
    for rel in (io.COMPONENTS_FILE, io.ORDERS_FILE, io.TIMELINE_FILE):
        left = pd.read_parquet(root / "a" / rel)
        right = pd.read_parquet(root / "b" / rel)
        pd.testing.assert_frame_equal(left, right)


# --- CTX-01: Stage H addendum run overrides + fail-closed resolution ---------


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
def addendum_world(tmp_path: Path) -> dict:
    """Synthetic anomaly + forensic runs and a forensic-addendum policy pin."""
    anom_root = tmp_path / "anomaly"
    for_root = tmp_path / "forensics"
    _write_run(anom_root, "anom_pin", "anomaly_fit_manifest.json", "anomaly")
    _write_run(anom_root, "anom_override", "anomaly_fit_manifest.json", "anomaly")
    # Forensic component string is not uniform across writers -> not checked.
    _write_run(for_root, "for_pin", "forensic_manifest.json", "forensics")
    _write_run(for_root, "for_override", "forensic_manifest.json", "forensics")
    fa = ForensicAddendumPolicy(
        enabled=True,
        anomaly_root=str(anom_root),
        anomaly_run_id="anom_pin",
        forensic_root=str(for_root),
        forensic_run_id="for_pin",
    )
    return {"policy": types.SimpleNamespace(forensic_addendum=fa)}


def _addendum_args(**overrides: object) -> argparse.Namespace:
    base = {"skip_addendum": False, "anomaly_run": None, "forensic_run": None}
    base.update(overrides)
    return argparse.Namespace(**base)


def test_bom_cli_overrides_parsed() -> None:
    args = run_bom_context._parse_args(["--anomaly-run", "A", "--forensic-run", "F"])
    assert args.anomaly_run == "A"
    assert args.forensic_run == "F"
    assert run_bom_context._parse_args([]).anomaly_run is None
    assert run_bom_context._parse_args([]).forensic_run is None


def test_bom_config_pin_used_when_no_override(addendum_world: dict) -> None:
    anomaly_dir, forensic_dir = run_bom_context._resolve_addendum_dirs(
        addendum_world["policy"], _addendum_args()
    )
    assert anomaly_dir is not None and anomaly_dir.name == "anom_pin"
    assert forensic_dir is not None and forensic_dir.name == "for_pin"


def test_bom_override_beats_config_pin(addendum_world: dict) -> None:
    anomaly_dir, forensic_dir = run_bom_context._resolve_addendum_dirs(
        addendum_world["policy"],
        _addendum_args(anomaly_run="anom_override", forensic_run="for_override"),
    )
    assert anomaly_dir is not None and anomaly_dir.name == "anom_override"
    assert forensic_dir is not None and forensic_dir.name == "for_override"


def test_bom_skip_addendum_requires_no_override(addendum_world: dict) -> None:
    anomaly_dir, forensic_dir = run_bom_context._resolve_addendum_dirs(
        addendum_world["policy"], _addendum_args(skip_addendum=True)
    )
    assert anomaly_dir is None and forensic_dir is None


def test_bom_stale_pin_fails_closed(addendum_world: dict) -> None:
    addendum_world["policy"].forensic_addendum.anomaly_run_id = "does-not-exist"
    with pytest.raises(BomContextBlockerError) as exc:
        run_bom_context._resolve_addendum_dirs(
            addendum_world["policy"], _addendum_args()
        )
    assert "--anomaly-run" in str(exc.value)
    assert "does-not-exist" in str(exc.value)


def test_bom_valid_override_selects_addendum_path(addendum_world: dict) -> None:
    addendum_world["policy"].forensic_addendum.anomaly_run_id = "does-not-exist"
    anomaly_dir, forensic_dir = run_bom_context._resolve_addendum_dirs(
        addendum_world["policy"], _addendum_args(anomaly_run="anom_override")
    )
    assert anomaly_dir is not None and anomaly_dir.name == "anom_override"
    assert forensic_dir is not None and forensic_dir.name == "for_pin"
