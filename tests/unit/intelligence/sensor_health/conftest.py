"""Fixtures for the Sensor Health Intelligence unit tests.

``ctx_factory`` builds a ready-to-evaluate :class:`SensorContext` (values +
profiles + train-window references) so each rule test states only the signal
shape it asserts on. Policy overrides ride through ``policy_overrides``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd
import pytest
from src.config import PROJECT_ROOT
from src.intelligence.sensor_health.policy import (
    SensorHealthPolicy,
    load_policy,
    resolve_sensor_meta,
)
from src.intelligence.sensor_health.rules import (
    RuleReferences,
    SensorContext,
    train_references,
)


@pytest.fixture(scope="session")
def sh_policy() -> SensorHealthPolicy:
    """Real policy loaded from configs/sensor_health_intelligence.yaml."""
    return load_policy(PROJECT_ROOT / "configs" / "sensor_health_intelligence.yaml")


@pytest.fixture
def policy_factory() -> Callable[..., SensorHealthPolicy]:
    def _make(**overrides: Any) -> SensorHealthPolicy:
        return SensorHealthPolicy.model_validate(overrides)

    return _make


@pytest.fixture
def baselines_factory() -> Callable[..., pd.DataFrame]:
    """Long-form baselines for every (profile, sensor) pair."""

    def _make(
        profiles: list[str],
        sensors: list[str],
        median: float = 50.0,
        iqr: float = 6.0,
        std: float = 5.0,
    ) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "profile": p,
                    "sensor": s,
                    "count": 500,
                    "median": median,
                    "iqr": iqr,
                    "std": std,
                }
                for p in profiles
                for s in sensors
            ]
        )

    return _make


@pytest.fixture
def ctx_factory(
    baselines_factory: Callable[..., pd.DataFrame],
) -> Callable[..., tuple[SensorContext, RuleReferences]]:
    """Build a SensorContext (+ refs) around one sensor's value array."""

    def _make(
        values: Any,
        profiles: list[str] | None = None,
        policy: SensorHealthPolicy | None = None,
        sensor: str = "s1",
        train_rows: int | None = None,
        baselines: pd.DataFrame | None = None,
    ) -> tuple[SensorContext, RuleReferences]:
        x = np.asarray(values, dtype=float)
        n = len(x)
        prof = np.array(profiles if profiles is not None else ["run"] * n, object)
        policy = policy or SensorHealthPolicy()
        train_mask = np.zeros(n, dtype=bool)
        train_mask[: train_rows if train_rows is not None else n] = True
        if baselines is None:
            baselines = baselines_factory(sorted(set(prof)), [sensor])
        df = pd.DataFrame(
            {sensor: x},
            index=pd.date_range("2024-09-01", periods=n, freq="1min"),
        )
        refs = train_references(df, [sensor], prof, train_mask, baselines, policy)
        change = np.zeros(n, dtype=bool)
        change[1:] = prof[1:] != prof[:-1]
        ctx = SensorContext(
            sensor=sensor,
            values=x,
            profiles=prof,
            train_mask=train_mask,
            profile_change=change,
            meta=resolve_sensor_meta(policy, sensor),
            refs=refs,
            policy=policy,
        )
        return ctx, refs

    return _make
