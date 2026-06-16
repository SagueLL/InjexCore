"""Run-versioning helpers: id minting, collision-safe creation, validated
completion semantics and resolution (ARC-02)."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from src.intelligence._common import runs

MANIFEST = "fit_manifest.json"


def _complete_manifest(run_id: str, component: str = "anomaly") -> dict:
    return {
        "component": component,
        "run_id": run_id,
        "completion_status": runs.COMPLETE,
    }


def _make_run(
    root: Path,
    run_id: str,
    *,
    manifest: dict | str | None,
) -> Path:
    """Create ``runs/<run_id>/`` and write its manifest.

    ``dict`` → JSON; ``str`` → raw bytes (to forge malformed JSON); ``None`` →
    no manifest at all (a crashed, half-written run).
    """
    d = root / runs.RUNS_SUBDIR / run_id
    d.mkdir(parents=True)
    if isinstance(manifest, dict):
        (d / MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    elif isinstance(manifest, str):
        (d / MANIFEST).write_text(manifest, encoding="utf-8")
    return d


# --- id minting -----------------------------------------------------------


def test_new_run_id_format(tmp_path: Path) -> None:
    run_id = runs.new_run_id(tmp_path)
    assert re.fullmatch(r"\d{8}T\d{6}Z", run_id)


def test_new_run_id_collision_suffix(tmp_path: Path) -> None:
    first = runs.new_run_id(tmp_path)
    (tmp_path / runs.RUNS_SUBDIR / first).mkdir(parents=True)
    # Same wall-clock second -> suffix must disambiguate, never reuse.
    now = datetime.now(UTC)
    a = runs.new_run_id(tmp_path, now=now)
    (tmp_path / runs.RUNS_SUBDIR / a).mkdir(parents=True)
    b = runs.new_run_id(tmp_path, now=now)
    assert a != b
    assert b.startswith(a.split("-")[0])


# --- collision-safe directory creation ------------------------------------


def test_create_run_dir_creates_fresh(tmp_path: Path) -> None:
    out = runs.create_run_dir(tmp_path, "myrun")
    assert out == tmp_path / runs.RUNS_SUBDIR / "myrun"
    assert out.is_dir()


def test_create_run_dir_rejects_existing_explicit_id(tmp_path: Path) -> None:
    runs.create_run_dir(tmp_path, "myrun")
    # An explicit --run-id pointing at an existing run must fail closed,
    # never overwrite or merge.
    with pytest.raises(runs.RunCollisionError):
        runs.create_run_dir(tmp_path, "myrun")


def test_create_run_dir_rejects_existing_completed_run(tmp_path: Path) -> None:
    _make_run(tmp_path, "myrun", manifest=_complete_manifest("myrun"))
    with pytest.raises(runs.RunCollisionError):
        runs.create_run_dir(tmp_path, "myrun")


def test_auto_run_id_then_create_never_collides(tmp_path: Path) -> None:
    rid = runs.new_run_id(tmp_path)
    runs.create_run_dir(tmp_path, rid)
    # A second auto id must route around the freshly created directory.
    nxt = runs.new_run_id(tmp_path)
    assert nxt != rid
    runs.create_run_dir(tmp_path, nxt)  # must not raise


# --- completion validation: resolution ------------------------------------


def test_resolve_latest_skips_incomplete_runs(tmp_path: Path) -> None:
    _make_run(
        tmp_path, "20260101T000000Z", manifest=_complete_manifest("20260101T000000Z")
    )
    _make_run(tmp_path, "20260102T000000Z", manifest=None)  # crashed run
    resolved = runs.resolve_run(tmp_path, "latest", MANIFEST)
    assert resolved.name == "20260101T000000Z"


def test_resolve_latest_picks_greatest_completed(tmp_path: Path) -> None:
    _make_run(
        tmp_path, "20260101T000000Z", manifest=_complete_manifest("20260101T000000Z")
    )
    _make_run(
        tmp_path, "20260103T000000Z", manifest=_complete_manifest("20260103T000000Z")
    )
    resolved = runs.resolve_run(tmp_path, "latest", MANIFEST)
    assert resolved.name == "20260103T000000Z"


def test_resolve_latest_no_runs_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="run the upstream component"):
        runs.resolve_run(tmp_path, "latest", MANIFEST)


def test_resolve_explicit_missing_or_incomplete_raises(tmp_path: Path) -> None:
    _make_run(tmp_path, "20260101T000000Z", manifest=None)
    with pytest.raises(FileNotFoundError, match="incomplete"):
        runs.resolve_run(tmp_path, "20260101T000000Z", MANIFEST)
    with pytest.raises(FileNotFoundError):
        runs.resolve_run(tmp_path, "nope", MANIFEST)


def test_resolve_explicit_completed(tmp_path: Path) -> None:
    _make_run(tmp_path, "myrun", manifest=_complete_manifest("myrun"))
    resolved = runs.resolve_run(tmp_path, "myrun", MANIFEST)
    assert resolved == tmp_path / runs.RUNS_SUBDIR / "myrun"


# --- manifest content is validated, not just presence ---------------------


def test_malformed_manifest_ignored(tmp_path: Path) -> None:
    _make_run(tmp_path, "20260101T000000Z", manifest="{ not valid json")
    assert runs.list_completed_runs(tmp_path, MANIFEST) == []
    with pytest.raises(FileNotFoundError):
        runs.resolve_run(tmp_path, "20260101T000000Z", MANIFEST)


def test_pending_manifest_ignored(tmp_path: Path) -> None:
    manifest = _complete_manifest("20260101T000000Z")
    manifest["completion_status"] = "pending"
    _make_run(tmp_path, "20260101T000000Z", manifest=manifest)
    assert runs.list_completed_runs(tmp_path, MANIFEST) == []


def test_missing_completion_status_ignored(tmp_path: Path) -> None:
    manifest = {"component": "anomaly", "run_id": "20260101T000000Z"}
    _make_run(tmp_path, "20260101T000000Z", manifest=manifest)
    assert runs.list_completed_runs(tmp_path, MANIFEST) == []


def test_wrong_run_id_manifest_ignored(tmp_path: Path) -> None:
    # Manifest claims a different run id than its own directory.
    manifest = _complete_manifest("some_other_id")
    _make_run(tmp_path, "20260101T000000Z", manifest=manifest)
    assert runs.list_completed_runs(tmp_path, MANIFEST) == []


def test_wrong_component_manifest_ignored(tmp_path: Path) -> None:
    _make_run(
        tmp_path,
        "20260101T000000Z",
        manifest=_complete_manifest("20260101T000000Z", component="pca"),
    )
    # Without an expected component, it resolves; with one, it must not.
    assert runs.list_completed_runs(tmp_path, MANIFEST) == ["20260101T000000Z"]
    assert (
        runs.list_completed_runs(tmp_path, MANIFEST, expected_component="anomaly") == []
    )
    with pytest.raises(FileNotFoundError):
        runs.resolve_run(tmp_path, "latest", MANIFEST, expected_component="anomaly")


def test_expected_component_match_accepted(tmp_path: Path) -> None:
    _make_run(
        tmp_path,
        "20260101T000000Z",
        manifest=_complete_manifest("20260101T000000Z", component="anomaly"),
    )
    resolved = runs.resolve_run(
        tmp_path, "latest", MANIFEST, expected_component="anomaly"
    )
    assert resolved.name == "20260101T000000Z"
