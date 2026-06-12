"""Context addendum: rate math, alignment gate, figures, manifest-last."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from src.context.operational import forensic_addendum as fa
from src.context.operational.overlay import build_overlay
from src.context.operational.policy import (
    ContextKeyPolicy,
    OperationalContextPolicy,
    SteamPolicy,
)
from src.context.operational.steam import (
    classify_steam_context,
    steam_activity_indicator,
)
from src.context.operational.validation import OperationalContextBlockerError


@pytest.fixture
def world(
    tmp_path: Path,
    master_ts_factory,
    profiles_factory,
    steam_frame_factory,
    health_timeline_factory,
    bom_timeline_factory,
) -> dict:
    periods = 600
    master_ts = master_ts_factory(periods)
    steam_df = steam_frame_factory(periods)
    steam_policy = SteamPolicy(window_rows=31, min_valid_rows=10)
    steam_ctx = classify_steam_context(
        steam_activity_indicator(steam_df, steam_policy), steam_df, steam_policy
    )
    overlay = build_overlay(
        master_ts,
        profiles_factory(periods),
        pd.Series([True] * 300 + [False] * 300),
        steam_ctx,
        health_timeline_factory(periods, faulty=(450, 600)),
        bom_timeline_factory(periods),
        ContextKeyPolicy(),
    )
    anomaly_dir = tmp_path / "anomaly_run"
    (anomaly_dir / "scores").mkdir(parents=True)
    severity = ["anomaly" if i >= 450 else "normal" for i in range(periods)]
    pd.DataFrame(
        {
            "timestamp": master_ts,
            "severity": severity,
            "combined_score": 0.5,
        }
    ).to_parquet(anomaly_dir / "scores" / "anomaly_scores.parquet", index=False)
    forensic_dir = tmp_path / "forensic_run"
    forensic_dir.mkdir()
    transitions = pd.DataFrame(
        {
            "transition_timestamp": [master_ts.iloc[450]],
            "transition_types": ["sensor_health_change"],
        }
    )
    policy = OperationalContextPolicy.model_validate(
        {
            "forensic_addendum": {
                "candidate_dates": [str(master_ts.iloc[450].date())],
                "window_hours": 12,  # row 450 = 07:30 on day one
            }
        }
    )
    return {
        "overlay": overlay,
        "transitions": transitions,
        "policy": policy,
        "anomaly_dir": anomaly_dir,
        "forensic_dir": forensic_dir,
    }


def test_rates_by_math() -> None:
    merged = pd.DataFrame(
        {
            "steam_context": ["on"] * 4 + ["off"] * 4,
            "is_train": [True, True, False, False] * 2,
            "is_anomaly": [False, False, True, False] + [False] * 4,
            "is_warning": [False] * 8,
        }
    )
    rates = fa._rates_by(merged, "steam_context").set_index("steam_context")
    assert rates.loc["on", "anomaly_rate_validation"] == 0.5
    assert rates.loc["off", "anomaly_rate_validation"] == 0.0
    assert rates.loc["on", "n_validation_rows"] == 2


def test_alignment_gate_raises_on_mismatch(world: dict) -> None:
    with pytest.raises(OperationalContextBlockerError, match="align"):
        fa._merge_scores(world["overlay"].iloc[:-1], world["anomaly_dir"])


def test_build_and_write_addendum(world: dict, tmp_path: Path) -> None:
    art = fa.build_addendum(
        world["overlay"],
        world["transitions"],
        world["policy"],
        "testrun",
        world["anomaly_dir"],
        world["forensic_dir"],
    )
    by_health = art.tables["anomaly_rates_by_sensor_health_context"].set_index(
        "sensor_health_context"
    )
    assert by_health.loc["sensor_faulty", "anomaly_rate_validation"] == 1.0
    assert "temporal associations" in art.executive_summary
    assert "causal" in art.limitations
    candidates = art.tables["candidate_dates_context_summary"]
    assert candidates.loc[0, "n_transitions_in_window"] == 1

    out = tmp_path / "addendum_out"
    written = fa.write_addendum(art, out)
    for fig in fa.FIGURES:
        assert (out / "figures" / fig).exists()
    manifest = json.loads(
        (out / fa.io.ADDENDUM_MANIFEST_NAME).read_text(encoding="utf-8")
    )
    assert manifest["completion_status"] == "complete"
    assert manifest["read_only"] is True
    assert written[-1] == fa.io.ADDENDUM_MANIFEST_NAME  # manifest written last
    for name in manifest["generated_files"]:
        assert (out / name).exists()
