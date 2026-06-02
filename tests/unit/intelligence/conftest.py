"""Fixtures for the Behaviour Intelligence unit tests.

Reuses the session-scoped ``groups`` and ``tiny_frame_factory`` fixtures
from the root ``tests/conftest.py``. ``tiny_frame_factory`` only builds the
~38 columns in ``variable_classification.csv`` — the feature-engineering
operative columns (``n_subsystems_running``, ``time_since_machine_off``,
``time_since_any_alarm``, ``any_alarm_while_running``) are added here by the
``behaviour_frame`` factory so profile/baseline tests have a master-like frame.
"""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd
import pytest
from src.config import PROJECT_ROOT
from src.intelligence.behaviour.policy import BehaviourPolicy, load_policy


@pytest.fixture(scope="session")
def behaviour_policy() -> BehaviourPolicy:
    """Real policy loaded from configs/behaviour_intelligence.yaml."""
    return load_policy(PROJECT_ROOT / "configs" / "behaviour_intelligence.yaml")


@pytest.fixture
def behaviour_frame(
    tiny_frame_factory: Callable[..., pd.DataFrame],
) -> Callable[..., pd.DataFrame]:
    """Factory returning a timestamp-indexed master-like frame.

    Adds the feature-engineering operative columns the profile rules read,
    defaulting to "machine fully running, no alarms". Tests mutate only the
    columns relevant to the behaviour under test.
    """

    def _make(
        n_rows: int = 40,
        n_subsystems: float = 3.0,
        production: float = 10.0,
    ) -> pd.DataFrame:
        df = tiny_frame_factory(n_rows=n_rows).set_index("timestamp")
        df["n_subsystems_running"] = float(n_subsystems)
        df["time_since_machine_off"] = 0.0
        df["time_since_any_alarm"] = 9999.0
        df["any_alarm_while_running"] = 0
        df["granulator_production_rate"] = float(production)
        return df

    return _make
