"""Run-versioning helpers: id minting, completion semantics, resolution."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from src.intelligence._common import runs


def _make_run(root: Path, run_id: str, *, complete: bool) -> None:
    d = root / runs.RUNS_SUBDIR / run_id
    d.mkdir(parents=True)
    if complete:
        (d / "fit_manifest.json").write_text("{}", encoding="utf-8")


def test_new_run_id_format(tmp_path: Path) -> None:
    run_id = runs.new_run_id(tmp_path)
    assert re.fullmatch(r"\d{8}T\d{6}Z", run_id)


def test_new_run_id_collision_suffix(tmp_path: Path) -> None:
    first = runs.new_run_id(tmp_path)
    (tmp_path / runs.RUNS_SUBDIR / first).mkdir(parents=True)
    # Same wall-clock second -> suffix must disambiguate, never reuse.
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    a = runs.new_run_id(tmp_path, now=now)
    (tmp_path / runs.RUNS_SUBDIR / a).mkdir(parents=True)
    b = runs.new_run_id(tmp_path, now=now)
    assert a != b
    assert b.startswith(a.split("-")[0])


def test_resolve_latest_skips_incomplete_runs(tmp_path: Path) -> None:
    _make_run(tmp_path, "20260101T000000Z", complete=True)
    _make_run(tmp_path, "20260102T000000Z", complete=False)  # crashed run
    resolved = runs.resolve_run(tmp_path, "latest", "fit_manifest.json")
    assert resolved.name == "20260101T000000Z"


def test_resolve_latest_picks_greatest_completed(tmp_path: Path) -> None:
    _make_run(tmp_path, "20260101T000000Z", complete=True)
    _make_run(tmp_path, "20260103T000000Z", complete=True)
    resolved = runs.resolve_run(tmp_path, "latest", "fit_manifest.json")
    assert resolved.name == "20260103T000000Z"


def test_resolve_latest_no_runs_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="run the upstream component"):
        runs.resolve_run(tmp_path, "latest", "fit_manifest.json")


def test_resolve_explicit_missing_or_incomplete_raises(tmp_path: Path) -> None:
    _make_run(tmp_path, "20260101T000000Z", complete=False)
    with pytest.raises(FileNotFoundError, match="incomplete"):
        runs.resolve_run(tmp_path, "20260101T000000Z", "fit_manifest.json")
    with pytest.raises(FileNotFoundError):
        runs.resolve_run(tmp_path, "nope", "fit_manifest.json")


def test_resolve_explicit_completed(tmp_path: Path) -> None:
    _make_run(tmp_path, "myrun", complete=True)
    resolved = runs.resolve_run(tmp_path, "myrun", "fit_manifest.json")
    assert resolved == tmp_path / runs.RUNS_SUBDIR / "myrun"
