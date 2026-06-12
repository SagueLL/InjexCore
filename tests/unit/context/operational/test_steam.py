"""Steam-context derivation: indicator semantics + persistence windows."""

from __future__ import annotations

import numpy as np
import pandas as pd
from src.context.operational.policy import SteamPolicy
from src.context.operational.steam import (
    classify_steam_context,
    steam_activity_indicator,
)


def _frame(pressure: list[float], temp: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2024-09-01", periods=len(pressure), freq="1min")
    return pd.DataFrame(
        {
            "steam_valve_pressure_me2": pressure,
            "conditioner_steam_loop_temp": temp,
        },
        index=idx,
    )


def test_indicator_or_semantics_and_nan_handling() -> None:
    policy = SteamPolicy()
    df = _frame(
        pressure=[2.5, 0.2, np.nan, np.nan, np.nan],
        temp=[30.0, 80.0, 86.0, 30.0, np.nan],
    )
    ind = steam_activity_indicator(df, policy)
    assert ind.tolist()[:2] == [1.0, 1.0]  # either signal can activate
    assert ind.iloc[2] == 1.0  # pressure NaN -> temp decides
    assert ind.iloc[3] == 0.0  # pressure NaN -> temp decides (inactive)
    assert np.isnan(ind.iloc[4])  # both NaN -> unknown indicator


def _classify(pressure: np.ndarray, temp: np.ndarray, **steam: object) -> pd.DataFrame:
    policy = SteamPolicy(window_rows=31, min_valid_rows=10, **steam)
    df = _frame(list(pressure), list(temp))
    return classify_steam_context(steam_activity_indicator(df, policy), df, policy)


def test_sustained_states_classified() -> None:
    n = 200
    off = _classify(np.full(n, 0.2), np.full(n, 34.0))
    assert (off["steam_context"] == "steam_conditioning_off").all()
    on = _classify(np.full(n, 2.6), np.full(n, 86.0))
    assert (on["steam_context"] == "steam_conditioning_on").all()
    assert (on["steam_context_confidence"] > 0.5).all()


def test_toggling_is_intermittent() -> None:
    n = 200
    pressure = np.where(np.arange(n) // 10 % 2 == 0, 2.6, 0.2)
    temp = np.where(np.arange(n) // 10 % 2 == 0, 86.0, 34.0)
    result = _classify(pressure, temp)
    middle = result["steam_context"].iloc[50:150]
    assert (middle == "steam_conditioning_intermittent").all()


def test_single_row_spike_never_flips_the_context() -> None:
    n = 200
    pressure = np.full(n, 0.2)
    pressure[100] = 6.0  # one isolated spike
    result = _classify(pressure, np.full(n, 34.0))
    assert (result["steam_context"] == "steam_conditioning_off").all()


def test_unknown_when_too_few_valid_rows() -> None:
    n = 100
    result = _classify(np.full(n, np.nan), np.full(n, np.nan))
    assert (result["steam_context"] == "unknown").all()
    assert (result["steam_context_confidence"] == 0.0).all()


def test_evidence_string_carries_window_facts() -> None:
    n = 60
    result = _classify(np.full(n, 2.6), np.full(n, 86.0))
    evidence = result["steam_context_evidence"].iloc[30]
    assert "f=1.000" in evidence
    assert "p_med=2.60" in evidence
    assert "t_med=86.00" in evidence
