"""Startup prewarm: warm the caches, but never let startup decide the contract.

The autouse `_no_prewarm` fixture in conftest disables prewarm for every other API
test (an un-guarded prewarm would drive real parquet reads for the four services a
given test file does not monkeypatch). These tests re-enable it deliberately.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from src.api.errors import ArtifactUnreadableError
from src.api.main import app
from src.api.services import (
    drift_anomaly,
    incidents,
    lineage_gate,
    overview,
    prewarm,
    sensor_health,
    timeline,
)
from src.api.services.lineage_gate import ApiLineageResult

from tests.api.conftest import lineage

_BUILDERS = (
    (sensor_health, "build_sensor_health_response"),
    (overview, "build_overview_response"),
    (timeline, "build_timeline_response"),
    (drift_anomaly, "build_drift_anomaly_response"),
    (incidents, "build_incidents_response"),
)


@pytest.fixture
def prewarm_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Undo conftest's autouse opt-out for this module's tests."""
    monkeypatch.delenv(prewarm.PREWARM_ENV_VAR, raising=False)


@pytest.fixture
def stub_builders(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, int]]:
    """Replace every view builder with a counter; no artifact is ever touched."""
    calls: dict[str, int] = {}

    def _counter(name: str) -> Callable[[], str]:
        def _build() -> str:
            calls[name] = calls.get(name, 0) + 1
            return name

        return _build

    for module, attr in _BUILDERS:
        monkeypatch.setattr(module, attr, _counter(attr))
    yield calls


def test_prewarm_enabled_defaults_to_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(prewarm.PREWARM_ENV_VAR, raising=False)
    assert prewarm.prewarm_enabled() is True


@pytest.mark.parametrize(("value", "expected"), [("0", False), ("1", True), ("", True)])
def test_prewarm_enabled_reads_the_env_var_at_call_time(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: bool
) -> None:
    monkeypatch.setenv(prewarm.PREWARM_ENV_VAR, value)
    assert prewarm.prewarm_enabled() is expected


def test_lifespan_prewarms_every_view_once(
    monkeypatch: pytest.MonkeyPatch,
    patch_lineage: Callable[[ApiLineageResult], None],
    prewarm_enabled: None,
    stub_builders: dict[str, int],
) -> None:
    patch_lineage(lineage("ok"))
    with TestClient(app):
        pass
    assert stub_builders == {attr: 1 for _, attr in _BUILDERS}


def test_lifespan_prewarms_on_a_warning_lineage(
    patch_lineage: Callable[[ApiLineageResult], None],
    prewarm_enabled: None,
    stub_builders: dict[str, int],
) -> None:
    # The canonical chain is "warning" (PROV-01); prewarm must still run.
    patch_lineage(lineage("warning"))
    with TestClient(app):
        pass
    assert len(stub_builders) == len(_BUILDERS)


def test_lifespan_skips_prewarm_behind_a_closed_gate(
    patch_lineage: Callable[[ApiLineageResult], None],
    prewarm_enabled: None,
    stub_builders: dict[str, int],
) -> None:
    # Fail closed: those endpoints answer 503 LINEAGE_INVALID regardless, and
    # touching artifacts behind a failed gate would violate the trust model.
    patch_lineage(lineage("invalid", is_valid=False))
    with TestClient(app):
        pass
    assert stub_builders == {}


def test_lifespan_skips_prewarm_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
    patch_lineage: Callable[[ApiLineageResult], None],
    stub_builders: dict[str, int],
) -> None:
    monkeypatch.setenv(prewarm.PREWARM_ENV_VAR, "0")
    patch_lineage(lineage("ok"))
    with TestClient(app):
        pass
    assert stub_builders == {}


def test_prewarm_views_never_raises_and_reports_survivors(
    monkeypatch: pytest.MonkeyPatch, stub_builders: dict[str, int]
) -> None:
    def _raise() -> None:
        raise ArtifactUnreadableError()

    monkeypatch.setattr(timeline, "build_timeline_response", _raise)
    warmed = prewarm.prewarm_views()
    assert "timeline" not in warmed
    assert {"sensor-health", "overview", "drift-anomaly", "incidents"} <= set(warmed)


def test_prewarm_views_survives_an_unexpected_exception(
    monkeypatch: pytest.MonkeyPatch, stub_builders: dict[str, int]
) -> None:
    # Startup must not die on a surprise (a schema change, a bad cell, anything).
    def _explode() -> None:
        raise RuntimeError("unexpected")

    monkeypatch.setattr(incidents, "build_incidents_response", _explode)
    assert "incidents" not in prewarm.prewarm_views()


def test_failed_prewarm_leaves_the_endpoint_contract_intact(
    monkeypatch: pytest.MonkeyPatch,
    patch_lineage: Callable[[ApiLineageResult], None],
    prewarm_enabled: None,
) -> None:
    # A crashed process would replace a documented 503 with connection-refused.
    #
    # Patch the timeline *loader*, not its builder: routes/dashboard.py imported
    # build_timeline_response by value at module load, so a module-attribute patch
    # would never reach the endpoint. Prewarm and the route share the one real
    # lru_cached builder object — which is exactly the coupling under test.
    calls = {"count": 0}

    def _raise() -> None:
        calls["count"] += 1
        raise ArtifactUnreadableError()

    for module, attr in _BUILDERS:
        if module is not timeline:
            monkeypatch.setattr(module, attr, lambda: None)
    timeline.build_timeline_response.cache_clear()
    monkeypatch.setattr(timeline, "_load_artifacts", _raise)
    patch_lineage(lineage("ok"))
    with TestClient(app) as client:
        # /health reads nothing and must stay green through a prewarm failure.
        assert client.get("/api/v1/health").status_code == 200
        resp = client.get("/api/v1/dashboard/timeline")
    timeline.build_timeline_response.cache_clear()
    assert resp.status_code == 503
    assert resp.json() == {
        "error": {
            "code": "ARTIFACT_UNREADABLE",
            "message": "A required artifact could not be read.",
        }
    }
    # Prewarm attempted it, then the request retried: exceptions are not cached.
    assert calls["count"] == 2


def test_health_is_green_when_lineage_is_invalid(
    patch_lineage: Callable[[ApiLineageResult], None], prewarm_enabled: None
) -> None:
    # Liveness must not depend on artifacts or on the lineage gate.
    patch_lineage(lineage("invalid", is_valid=False))
    with TestClient(app) as client:
        resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_prewarm_builds_sensor_health_before_overview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # /overview derives its problematic-sensor KPI through sensor-health's cache.
    order: list[str] = []
    for module, attr in _BUILDERS:
        monkeypatch.setattr(module, attr, (lambda a=attr: order.append(a)))
    prewarm.prewarm_views()
    assert order.index("build_sensor_health_response") < order.index(
        "build_overview_response"
    )


def test_lineage_gate_is_evaluated_before_prewarm(
    monkeypatch: pytest.MonkeyPatch,
    prewarm_enabled: None,
    stub_builders: dict[str, int],
) -> None:
    events: list[str] = []

    def _evaluate() -> ApiLineageResult:
        events.append("lineage")
        return lineage("ok")

    monkeypatch.setattr(lineage_gate, "evaluate_lineage", _evaluate)
    monkeypatch.setattr(
        timeline, "build_timeline_response", lambda: events.append("prewarm")
    )
    with TestClient(app):
        pass
    assert events[0] == "lineage"
    assert "prewarm" in events
