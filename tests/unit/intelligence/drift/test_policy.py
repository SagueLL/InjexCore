"""Policy schema: strict validation, taxonomies, real YAML round-trip."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from src.intelligence.drift.policy import (
    DRIFT_SEVERITIES,
    DRIFT_TYPES,
    EVENT_STATUSES,
    SCOPES,
    TEMPORAL_SHAPES,
    UNIVARIATE_METRICS,
    VIEWS,
    DriftPolicy,
    severity_from_score,
)


def test_real_yaml_loads(drift_policy: DriftPolicy) -> None:
    assert drift_policy.windows.granularity == "daily"
    assert drift_policy.healthy_view.enabled
    assert drift_policy.healthy_view.multivariate_proxy
    assert drift_policy.sensor_health_override.promote_faulty_events
    assert set(drift_policy.univariate.enabled_metrics) == set(UNIVARIATE_METRICS)


def test_unknown_key_raises() -> None:
    with pytest.raises(ValidationError):
        DriftPolicy.model_validate({"windows": {"granularitty": "daily"}})


def test_taxonomies_are_the_contract() -> None:
    assert "sensor_drift" in DRIFT_TYPES
    assert "profile_composition_shift" in DRIFT_TYPES
    assert set(VIEWS) == {"raw", "healthy_only"}
    assert "episodic" in TEMPORAL_SHAPES
    assert "pending_review" in EVENT_STATUSES
    assert DRIFT_SEVERITIES == ("info", "warning", "anomaly", "critical")
    assert "multivariate" in SCOPES


def test_severity_from_score_uses_cuts() -> None:
    cuts = {"info": 0.0, "warning": 0.4, "anomaly": 0.6, "critical": 0.8}
    assert severity_from_score(0.1, cuts) == "info"
    assert severity_from_score(0.45, cuts) == "warning"
    assert severity_from_score(0.6, cuts) == "anomaly"
    assert severity_from_score(0.95, cuts) == "critical"
