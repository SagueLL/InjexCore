"""Dashboard endpoints: run identity/lineage meta + the view endpoints.

``/meta`` returns the approved canonical run identity plus the lineage-gate
status evaluated once at startup (cached on app.state.dashboard_lineage by the
lifespan). ``/overview``, ``/timeline``, ``/sensor-health``,
``/drift-anomaly`` and ``/incidents`` are ``{meta, data}`` view endpoints that
fail closed on invalid lineage. No endpoint reads artifacts per request:
``/meta`` and ``/overview`` serve static pins shared via
``src.api.services.view_meta``, while ``/timeline``, ``/sensor-health``,
``/drift-anomaly`` and ``/incidents`` read the pinned run's artifacts once at
first hit and cache the built response in-process.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from src.api.dependencies import require_valid_dashboard_lineage
from src.api.schemas.common import Envelope
from src.api.schemas.dashboard_meta import DashboardMeta
from src.api.schemas.drift_anomaly import DriftAnomalySummary
from src.api.schemas.incidents import IncidentsSummary
from src.api.schemas.overview import DashboardSummary
from src.api.schemas.sensor_health import SensorHealthSummary
from src.api.schemas.timeline import OperationalTimeline
from src.api.services.drift_anomaly import build_drift_anomaly_response
from src.api.services.incidents import build_incidents_response
from src.api.services.overview import build_overview_response
from src.api.services.sensor_health import build_sensor_health_response
from src.api.services.timeline import build_timeline_response
from src.api.services.view_meta import (
    CONTRACT_VERSION,
    DATA_GENERATED_AT,
    TRAIN_WINDOW_END,
)
from src.dashboard.contract import CANONICAL_BOM_RUN_ID, CANONICAL_RUN_ID

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get(
    "/meta",
    summary="Dashboard run identity and lineage gate",
    description=(
        "Returns the approved canonical run identity, train-window boundary, and "
        "the lineage-gate status evaluated once at startup. Returns 200 even when "
        "lineage severity is 'warning' or 'invalid' (it is the gate banner "
        "source); data endpoints fail closed on 'invalid'."
    ),
)
async def get_dashboard_meta(request: Request) -> DashboardMeta:
    return DashboardMeta(
        contract_version=CONTRACT_VERSION,
        run_id=CANONICAL_RUN_ID,
        bom_run_id=CANONICAL_BOM_RUN_ID,
        data_generated_at=DATA_GENERATED_AT,
        train_window_end=TRAIN_WINDOW_END,
        lineage=request.app.state.dashboard_lineage,
        required_warnings=[],
    )


@router.get(
    "/overview",
    summary="Executive overview summary (enveloped)",
    description=(
        "Returns the {meta, data} envelope for the Executive Overview view. "
        "Fails closed with 503 LINEAGE_INVALID when the startup lineage gate is "
        "missing or invalid; 'ok'/'warning' severities pass. Serves stable "
        "canonical-run values; no artifact reads per request."
    ),
    response_model_exclude_none=True,
    dependencies=[Depends(require_valid_dashboard_lineage)],
)
async def get_dashboard_overview() -> Envelope[DashboardSummary]:
    return build_overview_response()


@router.get(
    "/timeline",
    summary="Operational timeline (enveloped)",
    description=(
        "Returns the {meta, data} envelope for the Operational Timeline view, "
        "computed from the pinned run's persisted anomaly scores, incidents "
        "and drift events (read once at first hit, then cached in-process). "
        "Fails closed with 503 LINEAGE_INVALID when the startup lineage gate "
        "is missing or invalid, and 503 ARTIFACT_UNREADABLE when a pinned "
        "artifact cannot be read."
    ),
    response_model_exclude_none=True,
    dependencies=[Depends(require_valid_dashboard_lineage)],
)
def get_dashboard_timeline() -> Envelope[OperationalTimeline]:
    # Sync handler on purpose: the first-hit parquet read runs in FastAPI's
    # threadpool instead of blocking the event loop.
    return build_timeline_response()


@router.get(
    "/sensor-health",
    summary="Sensor health summary (enveloped)",
    description=(
        "Returns the {meta, data} envelope for the Sensor Health view, built "
        "from the pinned run's persisted sensor-health summary plus a "
        "master-dataset coverage computation (read once at first hit, then "
        "cached in-process). Fails closed with 503 LINEAGE_INVALID when the "
        "startup lineage gate is missing or invalid, and 503 "
        "ARTIFACT_UNREADABLE when a pinned artifact cannot be read."
    ),
    response_model_exclude_none=True,
    dependencies=[Depends(require_valid_dashboard_lineage)],
)
def get_dashboard_sensor_health() -> Envelope[SensorHealthSummary]:
    # Sync handler on purpose: the first-hit parquet reads run in FastAPI's
    # threadpool instead of blocking the event loop.
    return build_sensor_health_response()


@router.get(
    "/drift-anomaly",
    summary="Drift and anomaly intelligence (enveloped)",
    description=(
        "Returns the {meta, data} envelope for the Drift & Anomaly view: the "
        "evidence funnel KPIs, the daily anomaly-evidence series with residual "
        "review counts, per-detector evidence counts and the affected-signal "
        "ranking, built from the pinned run's persisted anomaly scores, "
        "incidents, drift events and scoring-experiment comparison tables "
        "(read once at first hit, then cached in-process). Fails closed with "
        "503 LINEAGE_INVALID when the startup lineage gate is missing or "
        "invalid, and 503 ARTIFACT_UNREADABLE when a pinned artifact cannot "
        "be read."
    ),
    response_model_exclude_none=True,
    dependencies=[Depends(require_valid_dashboard_lineage)],
)
def get_dashboard_drift_anomaly() -> Envelope[DriftAnomalySummary]:
    # Sync handler on purpose: the first-hit parquet read runs in FastAPI's
    # threadpool instead of blocking the event loop.
    return build_drift_anomaly_response()


@router.get(
    "/incidents",
    summary="Incidents intelligence (enveloped)",
    description=(
        "Returns the {meta, data} envelope for the Incidents view: all "
        "canonical-run incidents (never just the review pack) sorted by "
        "review-pack priority, then severity, then start date, built from the "
        "pinned run's persisted incidents, review pack and recommended "
        "actions (read once at first hit, then cached in-process). Fails "
        "closed with 503 LINEAGE_INVALID when the startup lineage gate is "
        "missing or invalid, and 503 ARTIFACT_UNREADABLE when a pinned "
        "artifact cannot be read."
    ),
    response_model_exclude_none=True,
    dependencies=[Depends(require_valid_dashboard_lineage)],
)
def get_dashboard_incidents() -> Envelope[IncidentsSummary]:
    # Sync handler on purpose: the first-hit parquet read runs in FastAPI's
    # threadpool instead of blocking the event loop.
    return build_incidents_response()
