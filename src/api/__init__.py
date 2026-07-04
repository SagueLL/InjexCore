"""InjexCore read-only dashboard API (Dashboard v0.2).

``API_VERSION`` tracks the dashboard API contract version (v0.2). It is
intentionally distinct from the ``injexcore`` package version in
``pyproject.toml`` (0.1.0): the package and the API surface version separately.
"""

from __future__ import annotations

SERVICE_NAME = "injexcore-api"
API_VERSION = "0.2"
