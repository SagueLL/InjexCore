"""Orchestrator CLI — --no-write, manifest-last, immutability."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pandas as pd
import pytest
from src.context.bom import io, run_bom_context

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
    from src.context.bom.validation import BomContextBlockerError

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
