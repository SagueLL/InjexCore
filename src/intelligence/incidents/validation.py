"""Gate checks for Incident Aggregation — upstream-run coherence.

Run resolution (completed runs only) already guarantees manifests exist; the
checks here cover cross-run coherence: the drift run incidents consumes should
have been built from the same sensor-health / anomaly / operational runs that
incidents resolves, or contexts and evidence diverge. DAT-01: divergence is a
**blocker** — the incident layer never reasons over an incoherent chain.
Nothing here mutates upstream state.
"""

from __future__ import annotations

from typing import Any

from src.intelligence._common import lineage
from src.intelligence._common.reporting import Finding

CHECK = "incidents"


class IncidentsBlockerError(RuntimeError):
    """A gate check failed; the run must stop, not degrade."""


def validate_upstream(
    upstream_manifests: dict[str, dict[str, Any]],
    resolved_run_ids: dict[str, str],
) -> tuple[dict[str, Any], list[Finding]]:
    """Cross-check the drift run's pins against the resolved runs (fail closed)."""
    findings: list[Finding] = []
    drift_upstream = upstream_manifests.get("drift", {}).get("upstream", {})
    compat: dict[str, Any] = {"run_ids": dict(resolved_run_ids)}

    pin_map = {
        "sensor_health": "sensor_health_run_id",
        "anomaly": "anomaly_run_id",
        "operational": "operational_context_run_id",
    }
    for name, key in pin_map.items():
        pinned = drift_upstream.get(key)
        resolved = resolved_run_ids.get(name)
        compat[f"drift_{name}_run_matches"] = pinned == resolved
        lineage.assert_run_pin(name, pinned, resolved, IncidentsBlockerError)
    return compat, findings
