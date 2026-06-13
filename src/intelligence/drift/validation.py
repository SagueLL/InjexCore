"""Gate A — upstream compatibility checks for Drift Intelligence.

Drift consumes five persisted runs plus behaviour's fixed-path artifacts;
every run's recorded dataset identity is cross-checked against the master
this run loads. Fingerprint mismatches are warn-findings (mirroring the
anomaly component); misalignment of the operational timeline or the
behaviour labels is a blocker — silently realigning would break the
leakage contract.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.intelligence._common.fingerprint import dataset_fingerprint, file_sha256
from src.intelligence._common.reporting import Finding, Severity

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
    """Cross-check every consumed run against the loaded master.

    ``upstream_manifests``/``resolved_run_ids`` are keyed by component name
    (anomaly, pca, correlation, sensor_health, operational). Returns
    ``(compat_checks, findings)``; raises :class:`DriftBlockerError` on
    timeline misalignment.
    """
    findings: list[Finding] = []
    own = dataset_fingerprint(df, master_path)
    own_file_sha = file_sha256(master_path)
    compat: dict[str, Any] = {"run_ids": dict(resolved_run_ids)}

    # Drift loads a column-projected master, so the upstream structural sha
    # (computed on all 566 columns) can never match a projected fingerprint.
    # The projection-invariant identity — row count and index span — is the
    # honest comparison.
    for name in ("anomaly", "pca", "correlation"):
        manifest = upstream_manifests.get(name, {})
        upstream_fp = manifest.get("dataset_fingerprint", {})
        matches = (
            upstream_fp.get("n_rows") == own["n_rows"]
            and upstream_fp.get("index_start") == own["index_start"]
            and upstream_fp.get("index_end") == own["index_end"]
        )
        compat[f"{name}_fingerprint_matches"] = matches
        if not matches:
            findings.append(
                Finding(
                    check=CHECK,
                    severity=Severity.IMPORTANT,
                    finding_type="upstream_dataset_mismatch",
                    column=name,
                    action_taken="proceed_with_warning",
                    evidence={
                        "run_id": resolved_run_ids.get(name),
                        "upstream_n_rows": upstream_fp.get("n_rows"),
                        "upstream_index_span": [
                            upstream_fp.get("index_start"),
                            upstream_fp.get("index_end"),
                        ],
                        "master_n_rows": own["n_rows"],
                        "master_index_span": [
                            own["index_start"],
                            own["index_end"],
                        ],
                    },
                )
            )

    for name in ("sensor_health", "operational"):
        manifest = upstream_manifests.get(name, {})
        sha = manifest.get("master_dataset_sha256")
        matches = sha == own_file_sha
        compat[f"{name}_master_sha_matches"] = matches
        if not matches:
            findings.append(
                Finding(
                    check=CHECK,
                    severity=Severity.IMPORTANT,
                    finding_type="upstream_master_sha_mismatch",
                    column=name,
                    action_taken="proceed_with_warning",
                    evidence={
                        "run_id": resolved_run_ids.get(name),
                        "upstream_sha256": sha,
                        "master_sha256": own_file_sha,
                    },
                )
            )

    # The operational run pins the sensor-health run its timeline merged —
    # drift's health mask must come from the same run, or contexts diverge.
    pinned = upstream_manifests.get("operational", {}).get("sensor_health_run_id")
    resolved = resolved_run_ids.get("sensor_health")
    compat["operational_sensor_health_run_matches"] = pinned == resolved
    if pinned is not None and pinned != resolved:
        findings.append(
            Finding(
                check=CHECK,
                severity=Severity.IMPORTANT,
                finding_type="sensor_health_run_divergence",
                action_taken="proceed_with_warning",
                evidence={
                    "operational_pinned_run": pinned,
                    "drift_resolved_run": resolved,
                },
            )
        )

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
