"""Gate A — upstream compatibility checks for Drift Intelligence.

Drift consumes five persisted runs plus behaviour's artifacts; every run's
recorded dataset identity is cross-checked against the master this run loads.
DAT-01: a semantic lineage mismatch (projected fingerprint, master sha, or a
pinned upstream run id) is a **blocker** — drift never reasons over an
incompatible upstream chain. Timeline/label misalignment is a blocker for the
same reason. Nothing here mutates upstream state.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.intelligence._common import lineage
from src.intelligence._common.fingerprint import dataset_fingerprint, file_sha256
from src.intelligence._common.reporting import Finding

CHECK = "drift"


class DriftBlockerError(RuntimeError):
    """A Gate A check failed; the run must stop, not degrade."""


def validate_upstream(
    df: pd.DataFrame,
    master_path: Any,
    upstream_manifests: dict[str, dict[str, Any]],
    operational_timeline: pd.DataFrame,
    resolved_run_ids: dict[str, str],
) -> tuple[dict[str, Any], list[Finding]]:
    """Cross-check every consumed run against the loaded master (fail closed).

    ``upstream_manifests``/``resolved_run_ids`` are keyed by component name
    (anomaly, pca, correlation, sensor_health, operational). Returns
    ``(compat_checks, findings)``; raises :class:`DriftBlockerError` on any
    lineage mismatch.
    """
    findings: list[Finding] = []
    own = dataset_fingerprint(df, master_path)
    own_file_sha = file_sha256(master_path)
    compat: dict[str, Any] = {"run_ids": dict(resolved_run_ids)}

    # Drift loads a column-projected master, so the upstream structural sha can
    # never match a projected fingerprint. The projection-invariant identity —
    # row count and index span — is the honest comparison, and a mismatch is a
    # blocker (DAT-01).
    for name in ("anomaly", "pca", "correlation"):
        manifest = upstream_manifests.get(name, {})
        compat[f"{name}_fingerprint_matches"] = lineage.fingerprint_matches(
            manifest, own
        )
        lineage.assert_fingerprint(name, manifest, own, DriftBlockerError)

    for name in ("sensor_health", "operational"):
        manifest = upstream_manifests.get(name, {})
        compat[f"{name}_master_sha_matches"] = (
            manifest.get("master_dataset_sha256") == own_file_sha
        )
        lineage.assert_master_sha(name, manifest, own_file_sha, DriftBlockerError)

    # The operational run pins the sensor-health run its timeline merged —
    # drift's health mask must come from the same run, or contexts diverge.
    pinned = upstream_manifests.get("operational", {}).get("sensor_health_run_id")
    resolved = resolved_run_ids.get("sensor_health")
    compat["operational_sensor_health_run_matches"] = pinned == resolved
    lineage.assert_run_pin("sensor_health", pinned, resolved, DriftBlockerError)

    if len(operational_timeline) != len(df) or not operational_timeline.index.equals(
        df.index
    ):
        raise DriftBlockerError(
            "Operational context timeline does not align with the master "
            f"({len(operational_timeline)} timeline rows vs {len(df)} master "
            "rows) — re-run the operational context layer."
        )
    compat["operational_timeline_aligned"] = True
    return compat, findings
