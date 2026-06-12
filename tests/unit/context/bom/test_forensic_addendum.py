"""Stage H — read-only addendum: rate math, alignment gate, outputs."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pandas as pd
import pytest
from src.context.bom import forensic_addendum as fa
from src.context.bom import timeline
from src.context.bom.policy import BomContextPolicy
from src.context.bom.validation import BomContextBlockerError

T = pd.Timestamp


@pytest.fixture
def small_world(
    orders_factory: Callable[..., pd.DataFrame],
    master_ts_factory: Callable[..., pd.DatetimeIndex],
    tmp_path: Path,
) -> dict:
    """Timeline + matching synthetic anomaly run + forensic run dirs."""
    orders = orders_factory(
        [
            {"order_id": "100"},
            {
                "order_id": "101",
                "start_timestamp": T("2024-09-02"),
                "end_timestamp": T("2024-09-03"),
                "product_code": "214",
                "recipe_version": "v2",
                "bom_signature": "sig-b",
            },
        ]
    )
    master_ts = master_ts_factory(periods=96)  # 4 days hourly
    tl, _ = timeline.build_context_timeline(orders, master_ts)
    transitions = pd.DataFrame(
        {
            "transition_timestamp": [T("2024-09-02")],
            "previous_order_id": ["100"],
            "next_order_id": ["101"],
            "previous_product_code": ["114"],
            "next_product_code": ["214"],
            "previous_recipe_context_key": ["114:v1:sig-a"],
            "next_recipe_context_key": ["214:v2:sig-b"],
            "transition_type": ["product_change"],
        }
    )
    train_end = T("2024-09-01 12:00")
    severity = ["anomaly" if ts > T("2024-09-02") else "normal" for ts in master_ts]
    anomaly_dir = tmp_path / "anomaly_run"
    (anomaly_dir / "scores").mkdir(parents=True)
    pd.DataFrame(
        {
            "timestamp": master_ts.to_numpy(),
            "profile": "mid_production",
            "severity": severity,
            "combined_score": 0.5,
        }
    ).to_parquet(anomaly_dir / "scores" / "anomaly_scores.parquet", index=False)
    (anomaly_dir / "anomaly_fit_manifest.json").write_text(
        json.dumps(
            {
                "fit_window": {"train_end": str(train_end)},
                "dataset_fingerprint": {"sha256": "abc123"},
            }
        ),
        encoding="utf-8",
    )
    forensic_dir = tmp_path / "forensic_run"
    forensic_dir.mkdir()
    events = timeline.event_windows(
        orders,
        transitions,
        pd.DataFrame(columns=["overlap_start", "overlap_end"]),
        pd.DataFrame(columns=["gap_start", "gap_end"]),
        pd.DataFrame({"order_id": ["100"], "material_code": ["1222"]}),
        BomContextPolicy().forensic_windows.model_copy(
            update={"candidate_dates": ["2024-09-02"]}
        ),
    )
    return {
        "timeline": tl,
        "orders": orders,
        "transitions": transitions,
        "events": events,
        "anomaly_dir": anomaly_dir,
        "forensic_dir": forensic_dir,
    }


def test_rates_by_math() -> None:
    merged = pd.DataFrame(
        {
            "product_code": ["a"] * 4 + ["b"] * 4,
            "is_train": [True, True, False, False] * 2,
            "is_anomaly": [False, False, True, False, False, False, False, False],
            "is_warning": [False] * 8,
            "combined_score": [0.1] * 8,
        }
    )
    rates = fa._rates_by(merged, "product_code").set_index("product_code")
    assert rates.loc["a", "anomaly_rate_validation"] == 0.5
    assert rates.loc["b", "anomaly_rate_validation"] == 0.0
    assert rates.loc["a", "anomaly_rate_train"] == 0.0
    assert rates.loc["a", "n_validation_rows"] == 2


def test_alignment_gate_raises_on_mismatch(small_world: dict) -> None:
    scores = pd.read_parquet(
        small_world["anomaly_dir"] / "scores" / "anomaly_scores.parquet"
    )
    with pytest.raises(BomContextBlockerError, match="align"):
        fa._merge_timeline_scores(
            small_world["timeline"].iloc[:-1], scores, T("2024-09-01")
        )


def test_build_and_write_addendum(small_world: dict, tmp_path: Path) -> None:
    policy = BomContextPolicy()
    art = fa.build_addendum(
        small_world["timeline"],
        small_world["orders"],
        small_world["transitions"],
        small_world["events"],
        policy,
        "testrun",
        small_world["anomaly_dir"],
        small_world["forensic_dir"],
    )
    # Per-product rates only use matched single-order rows.
    by_product = art.tables["anomaly_rates_by_product"]
    assert set(by_product["product_code"].dropna()) <= {"114", "214"}
    by_status = art.tables["anomaly_rates_by_context_status"].set_index(
        "bom_context_status"
    )
    assert "no_active_order" in by_status.index or "outside_bom_coverage" in (
        by_status.index
    )
    assert "temporal associations" in art.executive_summary
    assert "## 7." in art.executive_summary
    assert "causal" in art.limitations

    out = tmp_path / "addendum_out"
    written = fa.write_addendum(art, out)
    for fig in fa.FIGURES:
        assert (out / "figures" / fig).exists()
    manifest = json.loads(
        (out / fa.io.ADDENDUM_MANIFEST_NAME).read_text(encoding="utf-8")
    )
    assert manifest["completion_status"] == "complete"
    assert manifest["read_only"] is True
    assert manifest["upstream"]["anomaly_run_id"] == "anomaly_run"
    assert written[-1] == fa.io.ADDENDUM_MANIFEST_NAME  # manifest written last
    for name in manifest["generated_files"]:
        assert (out / name).exists()
