"""Stage 4b — specialised state / alarm features."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.data.time_series import state_features

_RUN = "granulator_g2_running"
_ALARM = "granulator_g2_alarm"


def _indexed(tiny_frame_factory, n: int) -> pd.DataFrame:
    return tiny_frame_factory(n_rows=n, period_s=60.0).set_index("timestamp")


def test_runfrac_matches_hand_calc(tiny_frame_factory, ts_policy, groups):
    df = _indexed(tiny_frame_factory, n=20)
    df[_RUN] = [1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0]
    findings = state_features.detect(df, ts_policy, groups)
    out = state_features.apply(df, findings, ts_policy, groups)
    col = f"{_RUN}_runfrac_15"
    assert col in out.columns
    # Row 0 has no history (closed='left') → NaN.
    assert pd.isna(out[col].iloc[0])
    # Row 15 sees the previous 15 samples: indices 0..14 with ten ones.
    expected = sum(df[_RUN].iloc[:15]) / 15
    assert out[col].iloc[15] == expected


def test_tsla_resets_on_activation_and_increments(tiny_frame_factory, ts_policy, groups):
    df = _indexed(tiny_frame_factory, n=10)
    # Activations at rows 2 and 6; rows before row 2 are pre-first-activation.
    df[_RUN] = [0, 0, 1, 0, 0, 0, 1, 0, 0, 0]
    findings = state_features.detect(df, ts_policy, groups)
    out = state_features.apply(df, findings, ts_policy, groups)
    tsla = out[f"{_RUN}_tsla"]
    # Pre-first-activation rows are NaN.
    assert pd.isna(tsla.iloc[0])
    assert pd.isna(tsla.iloc[1])
    # On activation, counter resets to 0.
    assert tsla.iloc[2] == 0
    # Increments through the off-run.
    assert tsla.iloc[3] == 1
    assert tsla.iloc[4] == 2
    assert tsla.iloc[5] == 3
    # Next activation resets again.
    assert tsla.iloc[6] == 0
    assert tsla.iloc[9] == 3


def test_edges_counts_rising_transitions(tiny_frame_factory, ts_policy, groups):
    df = _indexed(tiny_frame_factory, n=80)
    flag = np.zeros(80, dtype=float)
    # Two rising edges within the first 60 samples (at rows 5 and 30).
    flag[5:8] = 1
    flag[30:32] = 1
    df[_ALARM] = flag
    findings = state_features.detect(df, ts_policy, groups)
    out = state_features.apply(df, findings, ts_policy, groups)
    edges_col = f"{_ALARM}_edges_60"
    assert edges_col in out.columns
    # At row 60 the previous 60 samples (rows 0..59) contain both rising edges.
    assert out[edges_col].iloc[60] == 2
