"""DASH-02: read-only dashboard lineage validation over synthetic chains.

The validator is exercised against synthetic manifests under ``tmp_path`` (no
real-data dependency) via the injectable ``intelligence_dir`` / ``context_dir``
roots. The registry itself drives chain construction so the fixtures cannot
drift from the contract.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from src.dashboard.contract import (
    CANONICAL_BOM_RUN_ID,
    CANONICAL_RUN_ID,
    component_specs,
)
from src.dashboard.lineage import validate_dashboard_chain


def _build_chain(
    idir: Path,
    cdir: Path,
    run_id: str,
    bom_run_id: str,
    *,
    with_provenance: bool = True,
) -> None:
    """Write all 11 completed runs (manifest last) for one chain."""
    for spec in component_specs(idir, cdir):
        rid = run_id if spec.run_kind == "canonical" else bom_run_id
        run_path = spec.root / "runs" / rid
        run_path.mkdir(parents=True)
        manifest: dict[str, object] = {
            "component": spec.component,
            "run_id": rid,
            "completion_status": "complete",
        }
        if spec.is_leaf:
            upstream: dict[str, str] = {}
            if with_provenance:
                upstream["behaviour_run_id"] = run_id
            if spec.name == "anomaly":
                upstream["pca_run_id"] = run_id
            manifest["upstream"] = upstream
        (run_path / spec.manifest_name).write_text(
            json.dumps(manifest), encoding="utf-8"
        )


@pytest.fixture
def dirs(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "intelligence", tmp_path / "context"


def _snapshot(root: Path) -> set[Path]:
    return {p for p in root.rglob("*") if p.is_file()}


def test_canonical_chain_valid(dirs: tuple[Path, Path]) -> None:
    idir, cdir = dirs
    _build_chain(idir, cdir, CANONICAL_RUN_ID, CANONICAL_BOM_RUN_ID)
    v = validate_dashboard_chain(intelligence_dir=idir, context_dir=cdir)
    assert v.is_valid
    assert v.canonical_match
    assert v.severity == "ok"
    assert v.warnings == []
    assert all(s.resolves for s in v.component_statuses.values())
    assert len(v.component_statuses) == 11


def test_validator_is_read_only(dirs: tuple[Path, Path], tmp_path: Path) -> None:
    idir, cdir = dirs
    _build_chain(idir, cdir, CANONICAL_RUN_ID, CANONICAL_BOM_RUN_ID)
    before = _snapshot(tmp_path)
    validate_dashboard_chain(intelligence_dir=idir, context_dir=cdir)
    assert _snapshot(tmp_path) == before  # never writes


def test_wrong_run_id_invalid(dirs: tuple[Path, Path]) -> None:
    idir, cdir = dirs
    _build_chain(idir, cdir, CANONICAL_RUN_ID, CANONICAL_BOM_RUN_ID)
    v = validate_dashboard_chain(
        "does-not-exist", CANONICAL_BOM_RUN_ID, intelligence_dir=idir, context_dir=cdir
    )
    assert not v.is_valid
    assert v.severity == "invalid"
    assert not v.canonical_match


def test_non_canonical_completed_chain_warns(dirs: tuple[Path, Path]) -> None:
    """A fully valid but non-canonical chain is usable only with a warning."""
    idir, cdir = dirs
    _build_chain(idir, cdir, "remat-v9-stale", "bom-stale")
    v = validate_dashboard_chain(
        "remat-v9-stale", "bom-stale", intelligence_dir=idir, context_dir=cdir
    )
    assert v.is_valid
    assert not v.canonical_match
    assert v.severity == "warning"
    assert any("not the canonical chain" in w for w in v.warnings)


def test_missing_manifest_invalid(dirs: tuple[Path, Path]) -> None:
    idir, cdir = dirs
    _build_chain(idir, cdir, CANONICAL_RUN_ID, CANONICAL_BOM_RUN_ID)
    (idir / "drift" / "runs" / CANONICAL_RUN_ID / "drift_manifest.json").unlink()
    v = validate_dashboard_chain(intelligence_dir=idir, context_dir=cdir)
    assert not v.is_valid
    assert v.severity == "invalid"
    assert not v.component_statuses["drift"].resolves
    assert v.component_statuses["drift"].severity == "invalid"


def test_wrong_component_invalid(dirs: tuple[Path, Path]) -> None:
    idir, cdir = dirs
    _build_chain(idir, cdir, CANONICAL_RUN_ID, CANONICAL_BOM_RUN_ID)
    path = (
        idir
        / "reference"
        / "runs"
        / CANONICAL_RUN_ID
        / "reference_governance_manifest.json"
    )
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["component"] = "drift"  # right shape, wrong component
    path.write_text(json.dumps(manifest), encoding="utf-8")
    v = validate_dashboard_chain(intelligence_dir=idir, context_dir=cdir)
    assert not v.is_valid
    assert not v.component_statuses["reference"].component_match
    assert v.component_statuses["reference"].severity == "invalid"


def test_bom_mismatch_invalid(dirs: tuple[Path, Path]) -> None:
    idir, cdir = dirs
    _build_chain(idir, cdir, CANONICAL_RUN_ID, CANONICAL_BOM_RUN_ID)
    v = validate_dashboard_chain(
        CANONICAL_RUN_ID, "wrong-bom-run", intelligence_dir=idir, context_dir=cdir
    )
    assert not v.is_valid
    assert not v.component_statuses["bom"].resolves
    # The intelligence components still resolve — only BOM is the problem.
    assert v.component_statuses["anomaly"].resolves


def test_missing_behaviour_provenance_warns_not_invalid(
    dirs: tuple[Path, Path],
) -> None:
    """Decision 1: a canonical chain predating PROV-01 stays usable (warning)."""
    idir, cdir = dirs
    _build_chain(
        idir, cdir, CANONICAL_RUN_ID, CANONICAL_BOM_RUN_ID, with_provenance=False
    )
    v = validate_dashboard_chain(intelligence_dir=idir, context_dir=cdir)
    assert v.is_valid
    assert v.canonical_match
    assert v.severity == "warning"
    leaf = v.component_statuses["correlation"]
    assert leaf.resolves
    assert leaf.severity == "warning"
    assert any("behaviour provenance" in w for w in v.warnings)


def test_lineage_edges_track_recorded_pins(dirs: tuple[Path, Path]) -> None:
    idir, cdir = dirs
    _build_chain(idir, cdir, CANONICAL_RUN_ID, CANONICAL_BOM_RUN_ID)
    v = validate_dashboard_chain(intelligence_dir=idir, context_dir=cdir)
    edges = {(e.parent, e.child): e for e in v.lineage_edges}
    assert edges[("behaviour", "anomaly")].parent_run_id == CANONICAL_RUN_ID
    assert edges[("behaviour", "anomaly")].consistent
    assert edges[("pca", "anomaly")].parent_run_id == CANONICAL_RUN_ID
    assert edges[("pca", "anomaly")].consistent
