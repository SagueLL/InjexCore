"""Read-only lineage validation for the Technical Validation Dashboard.

:func:`validate_dashboard_chain` walks the canonical component registry and
reports whether the pinned chain is internally consistent and safe to surface.
It never writes, refits, approves or mutates an artifact — it only reads
manifests.

Run-selector rule (DASH-02): only the canonical, lineage-valid chain is
reported as authoritative (``is_valid and canonical_match``). Any other
completed run is surfaced as non-canonical / stale with explicit warnings, so a
future run selector cannot present it as valid. For the MVP the dashboard pins
:data:`~src.dashboard.contract.CANONICAL_RUN_ID` rather than offering a broad
dropdown.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.config import CONTEXT_DIR, INTELLIGENCE_DIR
from src.dashboard.contract import (
    CANONICAL_BOM_RUN_ID,
    CANONICAL_RUN_ID,
    ComponentSpec,
    ComponentStatus,
    DashboardChainValidation,
    LineageEdge,
    component_specs,
)
from src.intelligence._common.runs import COMPLETE, RUNS_SUBDIR, is_completed_run

#: Manifest field carrying explicit behaviour provenance (PROV-01).
_BEHAVIOUR_RUN_KEY = "behaviour_run_id"
#: Leaf components whose behaviour provenance feeds the lineage graph.
_BEHAVIOUR_CHILDREN = ("correlation", "pca", "anomaly", "sensor_health")


def _read_manifest(path: Path) -> dict[str, Any] | None:
    """Parse a manifest file; return ``None`` when missing or malformed."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _upstream(manifest: dict[str, Any] | None) -> dict[str, Any]:
    """The manifest's ``upstream`` block, or an empty dict."""
    if not manifest:
        return {}
    block = manifest.get("upstream")
    return block if isinstance(block, dict) else {}


def _component_status(
    spec: ComponentSpec, expected_run: str
) -> tuple[ComponentStatus, dict[str, Any] | None]:
    """Resolve one component's pinned run and report granular status."""
    run_path = spec.root / RUNS_SUBDIR / expected_run
    manifest = _read_manifest(run_path / spec.manifest_name)
    present = run_path.is_dir()
    manifest_valid = manifest is not None
    completion_complete = bool(
        manifest and manifest.get("completion_status") == COMPLETE
    )
    component_match = bool(manifest and manifest.get("component") == spec.component)
    run_id_match = bool(manifest and str(manifest.get("run_id")) == expected_run)
    # The authoritative resolve check reuses the run-versioning contract.
    resolves = is_completed_run(
        run_path, spec.manifest_name, expected_component=spec.component
    )

    warnings: list[str] = []
    severity: str = "ok"
    if not resolves:
        severity = "invalid"
        if not present:
            warnings.append(f"{spec.name}: no run directory at {run_path}.")
        else:
            warnings.append(
                f"{spec.name}: run {expected_run!r} is not a valid completed "
                f"{spec.component!r} run (manifest missing, malformed, pending, "
                "wrong run id, or wrong component)."
            )
    elif spec.is_leaf and not _upstream(manifest).get(_BEHAVIOUR_RUN_KEY):
        # PROV-01 / Decision 1: a canonical chain predating explicit behaviour
        # provenance is still usable — degrade to a warning, never invalid.
        severity = "warning"
        warnings.append(
            f"{spec.name}: manifest lacks explicit behaviour provenance "
            f"({_BEHAVIOUR_RUN_KEY}); regenerate on the next rematerialization."
        )

    status = ComponentStatus(
        name=spec.name,
        expected_run_id=expected_run,
        present=present,
        manifest_valid=manifest_valid,
        completion_complete=completion_complete,
        component_match=component_match,
        run_id_match=run_id_match,
        resolves=resolves,
        severity=severity,  # type: ignore[arg-type]
        warnings=warnings,
    )
    return status, manifest


def _lineage_edges(
    manifests: dict[str, dict[str, Any] | None], run_id: str
) -> list[LineageEdge]:
    """Build behaviour->leaf and pca->anomaly edges from recorded pins."""
    edges: list[LineageEdge] = []
    for child in _BEHAVIOUR_CHILDREN:
        parent_run = _upstream(manifests.get(child)).get(_BEHAVIOUR_RUN_KEY)
        edges.append(
            LineageEdge(
                parent="behaviour",
                child=child,
                parent_run_id=parent_run,
                consistent=parent_run == run_id,
            )
        )
    pca_run = _upstream(manifests.get("anomaly")).get("pca_run_id")
    edges.append(
        LineageEdge(
            parent="pca",
            child="anomaly",
            parent_run_id=pca_run,
            consistent=pca_run == run_id,
        )
    )
    return edges


def validate_dashboard_chain(
    run_id: str = CANONICAL_RUN_ID,
    bom_run_id: str = CANONICAL_BOM_RUN_ID,
    *,
    intelligence_dir: Path = INTELLIGENCE_DIR,
    context_dir: Path = CONTEXT_DIR,
) -> DashboardChainValidation:
    """Validate the dashboard chain at ``run_id`` / ``bom_run_id`` (read-only).

    Every registry component must resolve to a completed run of the expected
    component at its pinned run id. A missing/malformed/wrong-component/wrong-id
    manifest makes the chain ``is_valid=False``. Missing behaviour provenance on
    a leaf is a warning, not a failure. ``canonical_match`` is true only for the
    canonical run + BOM ids; a valid-but-non-canonical chain is reported with a
    warning so a run selector never presents it as authoritative.

    ``intelligence_dir`` / ``context_dir`` are injectable so tests can validate
    synthetic chains without any real-data dependency.
    """
    specs = component_specs(intelligence_dir, context_dir)
    statuses: dict[str, ComponentStatus] = {}
    manifests: dict[str, dict[str, Any] | None] = {}
    for spec in specs:
        expected = run_id if spec.run_kind == "canonical" else bom_run_id
        status, manifest = _component_status(spec, expected)
        statuses[spec.name] = status
        manifests[spec.name] = manifest

    edges = _lineage_edges(manifests, run_id)

    warnings: list[str] = []
    for status in statuses.values():
        warnings.extend(status.warnings)
    for edge in edges:
        # A recorded-but-divergent pin is a genuine inconsistency; an absent pin
        # is already reported by the leaf's provenance warning.
        if edge.parent_run_id is not None and not edge.consistent:
            warnings.append(
                f"lineage {edge.parent}->{edge.child}: recorded parent run "
                f"{edge.parent_run_id!r} != expected {run_id!r}."
            )

    legacy = intelligence_dir / "behaviour" / "behaviour_fit_manifest.json"
    if legacy.is_file():
        warnings.append(
            f"Legacy fixed-path behaviour artifact present at {legacy}; the "
            "dashboard must consume only the run-versioned behaviour run."
        )

    is_valid = all(status.resolves for status in statuses.values())
    canonical_match = run_id == CANONICAL_RUN_ID and bom_run_id == CANONICAL_BOM_RUN_ID
    if is_valid and not canonical_match:
        warnings.append(
            f"Chain {run_id!r}/{bom_run_id!r} is not the canonical chain "
            f"({CANONICAL_RUN_ID}/{CANONICAL_BOM_RUN_ID}); surface only as "
            "non-canonical/stale, never as authoritative."
        )

    if not is_valid:
        severity: str = "invalid"
    elif warnings or not canonical_match:
        severity = "warning"
    else:
        severity = "ok"

    return DashboardChainValidation(
        run_id=run_id,
        bom_run_id=bom_run_id,
        is_valid=is_valid,
        severity=severity,  # type: ignore[arg-type]
        canonical_match=canonical_match,
        component_statuses=statuses,
        warnings=warnings,
        lineage_edges=edges,
    )
