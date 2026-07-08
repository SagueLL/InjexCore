"""Startup prewarm of the five cached view builders.

Every view reads its parquet artifacts on first hit and caches the built envelope
(``lru_cache(maxsize=1)``; the pinned run is immutable). Deferring that to the
first click means an artifact failure surfaces in front of an audience. Prewarming
at startup moves the failure to the log, before anyone is watching.

Two invariants:

* **Never raise.** A failed build stays uncached — ``lru_cache`` does not cache
  exceptions — so the endpoint re-attempts on first request and returns its
  documented ``503 ARTIFACT_UNREADABLE`` envelope. Killing the process instead
  would replace a documented 503 with connection-refused, and would take
  ``/health`` (which reads nothing) down with it.
* **Never run behind a failed lineage gate.** The caller skips prewarm when
  ``severity == "invalid"``: those endpoints answer ``503 LINEAGE_INVALID``
  regardless, and touching artifacts behind a closed gate violates fail-closed.
"""

from __future__ import annotations

import logging
import os
from types import ModuleType

logger = logging.getLogger(__name__)

#: Set to "0" to skip the startup prewarm (API tests; fast local restarts).
PREWARM_ENV_VAR = "INJEXCORE_API_PREWARM"


def prewarm_enabled() -> bool:
    """Whether the lifespan should prewarm. Read at call time, never at import."""
    return os.getenv(PREWARM_ENV_VAR, "1") != "0"


def _builders() -> tuple[tuple[str, ModuleType, str], ...]:
    # Imported lazily and resolved via getattr, so monkeypatched builders in tests
    # are the ones actually invoked.
    from src.api.services import (
        drift_anomaly,
        incidents,
        overview,
        sensor_health,
        timeline,
    )

    return (
        # sensor_health first: /overview reads through its cache.
        ("sensor-health", sensor_health, "build_sensor_health_response"),
        ("overview", overview, "build_overview_response"),
        ("timeline", timeline, "build_timeline_response"),
        ("drift-anomaly", drift_anomaly, "build_drift_anomaly_response"),
        ("incidents", incidents, "build_incidents_response"),
    )


def prewarm_views() -> list[str]:
    """Build and cache every view once. Returns the names that succeeded.

    Sequential on purpose: the master-dataset, scenario-scores and anomaly-scores
    reads would otherwise peak concurrently for a one-off saving of a few seconds.
    Never raises.
    """
    builders = _builders()
    warmed: list[str] = []
    for name, module, attr in builders:
        try:
            getattr(module, attr)()
        except Exception:  # noqa: BLE001 - startup must survive any build failure
            logger.exception(
                "Dashboard view %r failed to prewarm; it will retry on first request "
                "and return its 503 error envelope if it fails again.",
                name,
            )
        else:
            warmed.append(name)
    # Uvicorn configures only its own loggers, so an app logger's INFO records are
    # dropped by the root level (WARNING) unless the operator configures logging.
    # A partial prewarm must be audible regardless, so it is logged at WARNING —
    # `logging.lastResort` emits WARNING and above even with no handlers at all.
    total = len(builders)
    if len(warmed) < total:
        logger.warning(
            "Prewarmed only %d/%d dashboard views; the rest will 503 until their "
            "artifacts become readable. Warmed: %s",
            len(warmed),
            total,
            ", ".join(warmed) or "none",
        )
    else:
        logger.info(
            "Prewarmed %d/%d dashboard views: %s", total, total, ", ".join(warmed)
        )
    return warmed
