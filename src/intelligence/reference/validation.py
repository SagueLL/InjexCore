"""Gate A checks for Reference Governance — upstream compatibility.

Two hard gates (stop, never degrade): the behaviour fit manifest must carry
a real train window (so ``reference_v1`` can be seeded honestly), and every
upstream run that records a master sha must have been fitted on *this* master
file. A mismatch means an upstream run is stale; governance must not reason
over incompatible evidence. Nothing here mutates upstream state.
"""

from __future__ import annotations

from typing import Any

from src.intelligence._common.reporting import Finding

CHECK = "reference_governance"


class ReferenceBlockerError(RuntimeError):
    """A Gate A check failed; the run must stop, not degrade."""


def validate_upstream(
    master_sha256: str,
    behaviour_manifest: dict[str, Any],
    upstream_manifests: dict[str, dict[str, Any]],
    run_ids: dict[str, str],
) -> tuple[dict[str, Any], list[Finding]]:
    """Block on missing/incompatible behaviour provenance or a stale upstream master."""
    fit_window = behaviour_manifest.get("fit_window") or {}
    if not fit_window.get("train_start") or not fit_window.get("train_end"):
        raise ReferenceBlockerError(
            "Behaviour fit manifest has no train window — cannot seed "
            "reference_v1. Re-run the behaviour component first."
        )
    # GOV-01: reference_v1 is seeded from behaviour's recorded master sha; it
    # must exist and match the current master, or provenance is unverifiable.
    behaviour_sha = behaviour_manifest.get("master_dataset_sha256")
    if not behaviour_sha:
        raise ReferenceBlockerError(
            "Behaviour fit manifest has no master_dataset_sha256 — cannot "
            "establish reference_v1 provenance. Re-run the behaviour component."
        )
    if behaviour_sha != master_sha256:
        raise ReferenceBlockerError(
            "Behaviour baseline was fitted on a different master "
            f"(sha {behaviour_sha} != current {master_sha256}); reference_v1 "
            "provenance is incompatible. Re-run behaviour on the current master."
        )
    findings: list[Finding] = []
    compat: dict[str, Any] = {
        "run_ids": dict(run_ids),
        "master_sha256": master_sha256,
        "behaviour_master_sha_matches": True,
    }
    for name, manifest in upstream_manifests.items():
        recorded = manifest.get("master_dataset_sha256")
        if recorded is None:
            compat[f"{name}_master_sha_recorded"] = False
            continue
        matches = recorded == master_sha256
        compat[f"{name}_master_sha_matches"] = matches
        if not matches:
            raise ReferenceBlockerError(
                f"Upstream {name} run was fitted on a different master "
                f"(sha {recorded} != {master_sha256}); re-run the upstream "
                "component before governance."
            )
    return compat, findings
