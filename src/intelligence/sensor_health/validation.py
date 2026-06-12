"""Gate A — upstream compatibility checks for Sensor Health.

Behaviour's manifest predates the dataset-fingerprint convention, so the
de-facto fingerprint is the strict ``align_labels`` index equality (enforced
by the orchestrator). The checks here cover the declared vocabulary and
scope; every result lands in the run manifest's ``compat_checks`` block.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.intelligence._common.reporting import Finding, Severity
from src.intelligence.sensor_health.policy import SensorHealthPolicy
from src.intelligence.sensor_health.rules import CHECK


class SensorHealthBlockerError(RuntimeError):
    """A Gate A check failed; the run must stop, not degrade."""


def _metadata_profile_names(policy: SensorHealthPolicy) -> set[str]:
    names = set(policy.sensors.defaults.expected_zero_during_profiles)
    names |= set(policy.sensors.defaults.allow_flatline_profiles)
    for override in policy.sensors.overrides.values():
        names |= set(override.expected_zero_during_profiles or [])
        names |= set(override.allow_flatline_profiles or [])
    return names


def validate_upstream(
    sensors: list[str],
    behaviour_manifest: dict[str, Any],
    baselines: pd.DataFrame,
    policy: SensorHealthPolicy,
) -> tuple[dict[str, Any], list[Finding]]:
    """Vocabulary + scope coherence against behaviour's persisted contract."""
    findings: list[Finding] = []
    profiles_fitted = set(behaviour_manifest.get("profiles_fitted", []))

    unknown_names = _metadata_profile_names(policy) - profiles_fitted
    if unknown_names:
        raise SensorHealthBlockerError(
            f"Sensor metadata names profiles {sorted(unknown_names)} that "
            f"behaviour never fitted ({sorted(profiles_fitted)}) — fix "
            "configs/sensor_health_intelligence.yaml"
        )

    upstream_sensors = set(behaviour_manifest.get("sensors", []))
    extra_scope = sorted(set(sensors) - upstream_sensors)
    if extra_scope:
        findings.append(
            Finding(
                check=CHECK,
                severity=Severity.IMPORTANT,
                finding_type="scope_extends_upstream",
                count=len(extra_scope),
                action_taken="proceed_with_warning",
                evidence={"sensors": extra_scope},
            )
        )

    baseline_profiles = set(baselines["profile"].astype(str).unique())
    stray = baseline_profiles - profiles_fitted
    if stray:
        findings.append(
            Finding(
                check=CHECK,
                severity=Severity.AWARE,
                finding_type="baseline_profiles_not_in_manifest",
                count=len(stray),
                action_taken="proceed_with_warning",
                evidence={"profiles": sorted(stray)},
            )
        )

    compat = {
        "profiles_fitted": sorted(profiles_fitted),
        "metadata_profiles_valid": True,
        "sensor_scope_within_upstream": not extra_scope,
        "baseline_profiles_consistent": not stray,
    }
    return compat, findings
