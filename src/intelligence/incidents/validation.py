"""Gate checks for Incident Aggregation — upstream-run coherence.

Run resolution (completed runs only) already guarantees manifests exist;
the checks here cover cross-run coherence: the drift run should consume the
same sensor-health / anomaly / operational runs that incidents resolves,
or contexts and evidence may diverge. Divergence is a warn-finding (the
incident layer still works, with documented caveats); nothing here mutates
upstream state.
"""

from __future__ import annotations

from typing import Any

from src.intelligence._common.reporting import Finding, Severity

CHECK = "incidents"


class IncidentsBlockerError(RuntimeError):
    """A gate check failed; the run must stop, not degrade."""


def validate_upstream(
    upstream_manifests: dict[str, dict[str, Any]],
    resolved_run_ids: dict[str, str],
) -> tuple[dict[str, Any], list[Finding]]:
    """Cross-check the drift run's pins against the resolved runs."""
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
        matches = pinned == resolved
        compat[f"drift_{name}_run_matches"] = matches
        if pinned is not None and not matches:
            findings.append(
                Finding(
                    check=CHECK,
                    severity=Severity.IMPORTANT,
                    finding_type="upstream_run_divergence",
                    column=name,
                    action_taken="proceed_with_warning",
                    evidence={
                        "drift_pinned_run": pinned,
                        "incidents_resolved_run": resolved,
                    },
                )
            )
    return compat, findings
