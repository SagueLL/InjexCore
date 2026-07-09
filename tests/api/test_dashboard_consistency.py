"""Cross-view numeric consistency.

The overview once served "Problematic sensors: 17" — the monitored-sensor *total*
— while /sensor-health derived 13 problematic + 4 healthy from the same run. A
stakeholder navigating between the two saw the system disagree with itself.

"Problematic sensors" is now derived through the sensor-health builder, so the
contradiction is impossible by construction; the synthetic tests below pin that
invariant. The overview's remaining pinned constants have no such runtime guard,
so the real-run tests cross-check each of them against the endpoint that owns the
underlying artifact. They skip when the canonical run is absent (CI without data).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from src.api.main import app
from src.api.services import drift_anomaly, incidents, sensor_health
from src.api.services.lineage_gate import ApiLineageResult
from src.config import CONTEXT_DIR, INTELLIGENCE_DIR
from src.dashboard.contract import (
    CANONICAL_BOM_RUN_ID,
    CANONICAL_RUN_ID,
    component_specs,
)
from src.intelligence.anomaly import io as anomaly_io
from src.intelligence.drift import io as drift_io
from src.intelligence.incidents import io as incidents_io
from src.intelligence.scoring_experiment import io as scoring_io
from src.intelligence.sensor_health import io as sensor_health_io

from tests.api.conftest import lineage

_BEHAVIOUR_MANIFEST = (
    INTELLIGENCE_DIR
    / "behaviour"
    / "runs"
    / CANONICAL_RUN_ID
    / "behaviour_fit_manifest.json"
)
_REQUIRED_RUNS = (
    (anomaly_io.ANOMALY_DIR, anomaly_io.MANIFEST_NAME),
    (drift_io.DRIFT_DIR, drift_io.MANIFEST_NAME),
    (incidents_io.INCIDENTS_DIR, incidents_io.MANIFEST_NAME),
    (scoring_io.SCORING_DIR, scoring_io.MANIFEST_NAME),
    (sensor_health_io.SENSOR_HEALTH_DIR, sensor_health_io.MANIFEST_NAME),
)
requires_real_run = pytest.mark.skipif(
    not _BEHAVIOUR_MANIFEST.exists()
    or not all(
        (root / "runs" / CANONICAL_RUN_ID / manifest).exists()
        for root, manifest in _REQUIRED_RUNS
    ),
    reason="canonical run artifacts not present",
)


def _kpis(client: TestClient, view: str) -> dict[str, int]:
    data = client.get(f"/api/v1/dashboard/{view}").json()["data"]
    key = "kpis" if view == "overview" else "summaryKpis"
    return {kpi["label"]: kpi["value"] for kpi in data[key]}


def _distribution(client: TestClient) -> dict[str, int]:
    data = client.get("/api/v1/dashboard/sensor-health").json()["data"]
    return {item["status"]: item["count"] for item in data["distribution"]}


# --------------------------------------------------------------------------
# Synthetic: the invariant itself.
# --------------------------------------------------------------------------


def test_overview_problematic_sensors_never_contradicts_sensor_health(
    patch_lineage: Callable[[ApiLineageResult], None],
    patched_sensor_health: None,
) -> None:
    patch_lineage(lineage("ok"))
    with TestClient(app) as client:
        overview = _kpis(client, "overview")
        health = _kpis(client, "sensor-health")
        distribution = _distribution(client)

    problematic = overview["Problematic sensors"]
    assert problematic == health["Review required"]
    assert problematic == (
        distribution["warning"] + distribution["critical"] + distribution["unknown"]
    )
    # The original bug: the pin held the monitored-sensor total, not the
    # problematic subset. A run with zero healthy sensors would make these equal,
    # so the fixture deliberately keeps one healthy sensor.
    assert distribution["healthy"] > 0
    assert problematic != sum(distribution.values())


def test_overview_problematic_sensors_tracks_the_artifact(
    patch_lineage: Callable[[ApiLineageResult], None],
    patched_sensor_health: None,
) -> None:
    # The 5-sensor fixture: healthy 1 / warning 1 / critical 2 / unknown 1.
    patch_lineage(lineage("ok"))
    with TestClient(app) as client:
        assert _kpis(client, "overview")["Problematic sensors"] == 4
        assert sum(_distribution(client).values()) == 5


# --------------------------------------------------------------------------
# Real run: the overview's remaining pins must match the owning endpoints.
# --------------------------------------------------------------------------


@pytest.fixture
def real_run_caches() -> Iterator[None]:
    # Every view builder is lru_cached module-globally; a synthetic envelope
    # cached by an earlier test would silently satisfy these assertions.
    builders = (
        sensor_health.build_sensor_health_response,
        incidents.build_incidents_response,
        drift_anomaly.build_drift_anomaly_response,
    )
    for builder in builders:
        builder.cache_clear()
    yield
    for builder in builders:
        builder.cache_clear()


@requires_real_run
def test_overview_problematic_sensors_is_13_of_17_on_the_canonical_run(
    patch_lineage: Callable[[ApiLineageResult], None], real_run_caches: None
) -> None:
    patch_lineage(lineage("ok"))
    with TestClient(app) as client:
        overview = _kpis(client, "overview")
        distribution = _distribution(client)
    # critical 3 + warning 7 + unknown 3 = 13 problematic; 4 healthy; 17 monitored.
    assert overview["Problematic sensors"] == 13
    assert distribution["healthy"] == 4
    assert sum(distribution.values()) == 17


@requires_real_run
def test_overview_incident_count_matches_the_incidents_view(
    patch_lineage: Callable[[ApiLineageResult], None], real_run_caches: None
) -> None:
    patch_lineage(lineage("ok"))
    with TestClient(app) as client:
        overview = _kpis(client, "overview")
        incident_kpis = _kpis(client, "incidents")
    assert overview["Detected incidents"] == incident_kpis["Total incidents"]


@requires_real_run
def test_overview_contextualised_anomalies_matches_the_drift_anomaly_view(
    patch_lineage: Callable[[ApiLineageResult], None], real_run_caches: None
) -> None:
    patch_lineage(lineage("ok"))
    with TestClient(app) as client:
        overview = _kpis(client, "overview")
        drift = _kpis(client, "drift-anomaly")
    assert overview["Contextualised anomalies"] == drift["Contextualised for review"]


@requires_real_run
def test_overview_copy_pins_match_the_drift_anomaly_funnel(
    patch_lineage: Callable[[ApiLineageResult], None], real_run_caches: None
) -> None:
    # _NON_NORMAL_ROWS and the residual backlog pins are interpolated into copy
    # rather than served as KPI values; assert the numbers, not the sentences.
    from src.api.services import overview as overview_service

    patch_lineage(lineage("ok"))
    with TestClient(app) as client:
        drift = _kpis(client, "drift-anomaly")
    assert drift["Raw non-normal rows"] == overview_service._NON_NORMAL_ROWS
    assert (
        drift["Residual review backlog"]
        == overview_service._RESIDUAL_ANOMALY_BACKLOG
        + overview_service._RESIDUAL_WARNING_BACKLOG
    )


@requires_real_run
def test_overview_total_records_matches_the_behaviour_manifest() -> None:
    from src.api.services import overview as overview_service

    manifest: dict[str, Any] = json.loads(
        _BEHAVIOUR_MANIFEST.read_text(encoding="utf-8")
    )
    assert manifest["train_window"]["n_total"] == overview_service._TOTAL_RECORDS


def _chain_completion_timestamps() -> list[str]:
    """Every pinned component's completion time, from its own manifest.

    Manifests record it under `created_at` OR `fit_timestamp` — the heterogeneity
    that keeps dataGeneratedAt pinned rather than derived at startup.
    """
    stamps = []
    for spec in component_specs(INTELLIGENCE_DIR, CONTEXT_DIR):
        expected = (
            CANONICAL_RUN_ID if spec.run_kind == "canonical" else CANONICAL_BOM_RUN_ID
        )
        manifest = json.loads(
            (spec.root / "runs" / expected / spec.manifest_name).read_text(
                encoding="utf-8"
            )
        )
        key = next(k for k in ("created_at", "fit_timestamp") if k in manifest)
        stamps.append(str(manifest[key]))
    return stamps


@requires_real_run
def test_data_generated_at_is_the_chain_completion_time() -> None:
    # dataGeneratedAt is the LATEST completion across the pinned chain — NOT the
    # behaviour fit time (behaviour completes first, 4h25m before the artifacts
    # this API actually serves) and not the run-id mint time.
    from src.api.services.view_meta import DATA_GENERATED_AT

    latest = max(_chain_completion_timestamps())
    assert f"{latest[:19]}Z" == DATA_GENERATED_AT

    behaviour_created_at = json.loads(_BEHAVIOUR_MANIFEST.read_text(encoding="utf-8"))[
        "created_at"
    ]
    assert latest > behaviour_created_at, "behaviour is not the last component"
