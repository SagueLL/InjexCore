"""Shared fixtures for the read-only dashboard API tests.

Two responsibilities:

* **Disable the startup prewarm.** ``with TestClient(app)`` runs the FastAPI
  lifespan, which (since the prewarm slice) builds all five views. Each test
  module monkeypatches only *its own* service's ``_load_artifacts``, so an
  un-guarded prewarm would drive real parquet reads for the other four views in
  every test. The autouse fixture below opts every API test out.
* **Share the synthetic sensor-health artifacts.** ``/overview`` derives its
  "Problematic sensors" KPI from the sensor-health view's cached builder, so
  both endpoints (and the cross-view consistency tests) need the same frames.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pandas as pd
import pytest
from src.api.services import lineage_gate, sensor_health
from src.api.services.lineage_gate import ApiLineageResult

SensorHealthLoader = Callable[[], tuple[pd.DataFrame, dict[str, float]]]


@pytest.fixture(autouse=True)
def _no_prewarm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opt every API test out of the lifespan's artifact prewarm."""
    monkeypatch.setenv("INJEXCORE_API_PREWARM", "0")


def lineage(severity: str, *, is_valid: bool = True) -> ApiLineageResult:
    """A canonical-match lineage result at ``severity``, with no warnings."""
    return ApiLineageResult(
        is_valid=is_valid, canonical_match=True, severity=severity, warnings=[]
    )


@pytest.fixture
def patch_lineage(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[ApiLineageResult], None]:
    """Fake the startup lineage evaluation so tests never touch real manifests."""

    def _patch(result: ApiLineageResult) -> None:
        monkeypatch.setattr(lineage_gate, "evaluate_lineage", lambda: result)

    return _patch


def _sensor_health_frames() -> tuple[pd.DataFrame, dict[str, float]]:
    # Five sensors exercising every §6 status arm, including the
    # quarantine-recommended OR-arm with zero faulty rows.
    # Derived statuses: healthy 1, warning 1, critical 2, unknown 1
    # -> 4 problematic of 5 total (the overview/sensor-health contract).
    summary = pd.DataFrame(
        {
            "sensor": [
                "s_healthy",
                "s_warning",
                "s_faulty",
                "s_quarantine",
                "s_unknown",
            ],
            "n_rows": [100] * 5,
            "n_healthy": [100, 95, 90, 100, 60],
            "n_warning": [0, 5, 0, 0, 0],
            "n_faulty": [0, 0, 10, 0, 0],
            "n_unknown": [0, 0, 0, 0, 40],
            "n_events": [0, 1, 2, 1, 0],
            "issue_row_counts": [
                "{}",
                '{"variance_explosion": 5}',
                '{"flatline_zero": 10}',
                "{}",
                "{}",
            ],
            "quarantine_recommended": [False, False, False, True, False],
        }
    )
    summary["issue_counts"] = summary["issue_row_counts"].map(
        sensor_health._parse_issue_counts
    )
    coverage = {
        "s_healthy": 100.0,
        "s_warning": 99.0,
        "s_faulty": 100.0,
        "s_quarantine": 100.0,
        "s_unknown": 42.0,
    }
    return summary, coverage


@pytest.fixture
def sensor_health_frames() -> SensorHealthLoader:
    """The synthetic ``sensor_health._load_artifacts`` replacement."""
    return _sensor_health_frames


@pytest.fixture
def patched_sensor_health(
    monkeypatch: pytest.MonkeyPatch, sensor_health_frames: SensorHealthLoader
) -> Iterator[None]:
    """Serve the synthetic sensor-health artifacts to every consumer.

    Clears before AND after: a leaked cached envelope would silently decouple
    later tests from their fixtures — and ``/overview`` now shares this cache.
    """
    sensor_health.build_sensor_health_response.cache_clear()
    monkeypatch.setattr(sensor_health, "_load_artifacts", sensor_health_frames)
    yield
    sensor_health.build_sensor_health_response.cache_clear()
