"""Behaviour Intelligence — operational profile segmentation."""

from __future__ import annotations

import pandas as pd
from src.intelligence.behaviour import profiles
from src.intelligence.behaviour.policy import BehaviourPolicy


def _all_train(df: pd.DataFrame) -> pd.Series:
    return pd.Series(True, index=df.index)


# Small transient windows so the regimes are isolated and deterministic.
_TIGHT = BehaviourPolicy.model_validate(
    {
        "profiles": {
            "startup": {"window_samples": 2},
            "shutdown": {"window_samples": 2},
            "alarm": {"window_samples": 0},
        }
    }
)


def test_stopped_when_machine_off(behaviour_frame, groups) -> None:
    df = behaviour_frame(n_rows=10)
    df["n_subsystems_running"] = [0.0] * 5 + [3.0] * 5
    art, _ = profiles.derive(df, _TIGHT, groups, train_mask=_all_train(df))
    assert (art.labels.iloc[:5] == profiles.STOPPED).all()


def test_startup_shutdown_transients(behaviour_frame, groups) -> None:
    df = behaviour_frame(n_rows=6)
    # on,on,on,on,off,off -> rising edge at 0, falling edge (1->0) at index 4.
    df["n_subsystems_running"] = [3.0, 3.0, 3.0, 3.0, 0.0, 0.0]
    art, _ = profiles.derive(df, _TIGHT, groups, train_mask=_all_train(df))
    assert art.labels.tolist() == [
        profiles.STARTUP,
        profiles.STARTUP,
        profiles.SHUTDOWN,
        profiles.SHUTDOWN,
        profiles.STOPPED,
        profiles.STOPPED,
    ]


def test_alarm_overrides_production(behaviour_frame, groups) -> None:
    df = behaviour_frame(n_rows=3)
    df["n_subsystems_running"] = 3.0
    # startup window 1 -> only index 0 is startup; index 1 has an active alarm.
    policy = BehaviourPolicy.model_validate(
        {"profiles": {"startup": {"window_samples": 1}, "alarm": {"window_samples": 0}}}
    )
    df["any_alarm_while_running"] = [0, 1, 0]
    art, _ = profiles.derive(df, policy, groups, train_mask=_all_train(df))
    assert art.labels.iloc[1] == profiles.ALARM


def test_production_tertiles(behaviour_frame, groups) -> None:
    df = behaviour_frame(n_rows=12)
    df["n_subsystems_running"] = 3.0
    df["granulator_production_rate"] = [float(i) for i in range(12)]
    policy = BehaviourPolicy.model_validate(
        {"profiles": {"startup": {"window_samples": 1}, "alarm": {"window_samples": 0}}}
    )
    art, _ = profiles.derive(df, policy, groups, train_mask=_all_train(df))
    # index 0 is the startup transient; 1..11 are production candidates (1..11).
    assert art.labels.iloc[1] == profiles.LOW_PROD
    assert art.labels.iloc[6] == profiles.MID_PROD
    assert art.labels.iloc[11] == profiles.HIGH_PROD
    assert art.production_edges  # quantile edges were fit


def test_unsupported_regimes_documented(behaviour_frame, groups) -> None:
    df = behaviour_frame(n_rows=8)
    _, findings = profiles.derive(df, _TIGHT, groups, train_mask=_all_train(df))
    documented = {
        f.column for f in findings if f.finding_type == "regime_not_derivable"
    }
    assert documented == {"cleaning", "maintenance", "recipe_change"}


def test_material_change_candidate_flag(behaviour_frame, groups) -> None:
    df = behaviour_frame(n_rows=4)
    df["batch_id"] = ["a", "a", "b", "b"]
    art, _ = profiles.derive(df, _TIGHT, groups, train_mask=_all_train(df))
    assert art.material_change is not None
    assert bool(art.material_change.iloc[2]) is True
    assert bool(art.material_change.iloc[0]) is False


def test_machine_state_undeterminable(behaviour_frame, groups) -> None:
    df = behaviour_frame(n_rows=5).drop(columns=["n_subsystems_running"])
    df = df.drop(columns=[c for c in groups.running_flags if c in df.columns])
    art, findings = profiles.derive(df, _TIGHT, groups, train_mask=_all_train(df))
    assert (art.labels == profiles.UNKNOWN).all()
    assert any(f.finding_type == "machine_state_undeterminable" for f in findings)
