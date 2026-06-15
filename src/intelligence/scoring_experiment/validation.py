"""Gate A checks for the Controlled Scoring Experiment.

Two hard gates (stop, never degrade): the persisted anomaly scores and the
operational context timeline must be row-aligned (the scenarios join them
per timestamp), and every upstream run that records a master sha must have
been fitted on *this* master. Nothing here mutates upstream state.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.intelligence._common.reporting import Finding

CHECK = "controlled_scoring_experiment"


class ScoringBlockerError(RuntimeError):
    """A Gate A check failed; the run must stop, not degrade."""


def validate_upstream(
    master_sha256: str,
    anomaly: pd.DataFrame,
    op_timeline: pd.DataFrame,
    upstream_manifests: dict[str, dict[str, Any]],
    run_ids: dict[str, str],
) -> tuple[dict[str, Any], list[Finding]]:
    """Block on a row-alignment break or a stale upstream master."""
    if len(anomaly) != len(op_timeline) or not anomaly.index.equals(op_timeline.index):
        raise ScoringBlockerError(
            "Anomaly scores and the operational context timeline are not "
            f"row-aligned ({len(anomaly)} vs {len(op_timeline)} rows) — the "
            "scenarios cannot join them. Re-run the upstream components."
        )
    findings: list[Finding] = []
    compat: dict[str, Any] = {
        "run_ids": dict(run_ids),
        "master_sha256": master_sha256,
        "rows": int(len(anomaly)),
    }
    for name, manifest in upstream_manifests.items():
        recorded = manifest.get("master_dataset_sha256")
        if recorded is None:
            compat[f"{name}_master_sha_recorded"] = False
            continue
        matches = recorded == master_sha256
        compat[f"{name}_master_sha_matches"] = matches
        if not matches:
            raise ScoringBlockerError(
                f"Upstream {name} run was fitted on a different master "
                f"(sha {recorded} != {master_sha256}); re-run the upstream "
                "component before the scoring experiment."
            )
    return compat, findings
