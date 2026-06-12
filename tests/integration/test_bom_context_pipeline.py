"""BOM context pipeline contract: raw CSV → timeline → forensic addendum.

Runs the real CLI end-to-end on a small synthetic world (CSV with overlap,
gap, recipe change and composition change; master parquet; persisted
synthetic anomaly + forensic runs) and verifies the master-alignment
contract, the overlap-preservation policy, manifest-as-completion-marker
and source immutability. No model fitting happens anywhere.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from src.context.bom import io, run_bom_context
from src.context.bom.forensic_addendum import FIGURES

_HEADERS = [
    "EQ56_ORDRE",
    "Fecha Incio",
    "Fecha Fin",
    "Producto",
    "Descripcion Producto",
    "Version",
    "Descripcion version",
    "Materia prima",
    "Descripcion materia prima",
    "Porcentaje",
    "Punto Dosificacion",
]

# A (114/v1) ← overlap → B (114/v2) ← gap → C (214/v1) ← composition → D (214/v1)
_CSV_ROWS = [
    (
        "100",
        "2024-09-01 00:00:00",
        "2024-09-01 00:40:00",
        "114",
        "CC-21",
        "v1",
        "r1",
        "1222",
        "HARINILLA DE MAIZ",
        "60,5",
        "PP",
    ),
    (
        "100",
        "2024-09-01 00:00:00",
        "2024-09-01 00:40:00",
        "114",
        "CC-21",
        "v1",
        "r1",
        "1901",
        "MAT B",
        "39,5",
        "DO",
    ),
    (
        "101",
        "2024-09-01 00:30:00",
        "2024-09-01 01:10:00",
        "114",
        "CC-21",
        "v2",
        "r2",
        "1222",
        "HARINILLA DE MAIZ",
        "100",
        "PP",
    ),
    (
        "102",
        "2024-09-01 01:30:00",
        "2024-09-01 02:00:00",
        "214",
        "CC-31",
        "v1",
        "r3",
        "1222",
        "HARINILLA DE MAIZ",
        "100",
        "PP",
    ),
    (
        "103",
        "2024-09-01 02:00:00",
        "2024-09-01 02:10:00",
        "214",
        "CC-31",
        "v1",
        "r3",
        "1222",
        "HARINILLA DE MAIZ",
        "99,5",
        "PP",
    ),
    (
        "103",
        "2024-09-01 02:00:00",
        "2024-09-01 02:10:00",
        "214",
        "CC-31",
        "v1",
        "r3",
        "1901",
        "MAT B",
        "0,5",
        "PP",
    ),
]

_N_MASTER = 200
_TRAIN_END = "2024-09-01 00:45:00"

_SCORE_COLUMNS = [
    "timestamp",
    "profile",
    "statistical_score",
    "mahalanobis_score",
    "pca_q_score",
    "pca_t2_score",
    "isolation_forest_score",
    "combined_score",
    "severity",
    "triggered_detectors",
    "affected_variables",
    "evidence",
]


@pytest.fixture
def world(tmp_path: Path) -> dict:
    """Synthetic CSV + master + completed anomaly/forensic runs + config."""
    csv_path = tmp_path / "bom.csv"
    pd.DataFrame(_CSV_ROWS, columns=_HEADERS).to_csv(
        csv_path, index=False, encoding="utf-8-sig"
    )

    master_ts = pd.date_range("2024-08-31 23:30:00", periods=_N_MASTER, freq="1min")
    master_path = tmp_path / "master.parquet"
    pd.DataFrame({"timestamp": master_ts, "sensor_a": 1.0}).to_parquet(
        master_path, index=False
    )

    anomaly_root = tmp_path / "anomaly"
    anomaly_run = anomaly_root / "runs" / "chain"
    (anomaly_run / "scores").mkdir(parents=True)
    severity = [
        "anomaly" if ts >= pd.Timestamp("2024-09-01 01:30:00") else "normal"
        for ts in master_ts
    ]
    scores = pd.DataFrame(
        {
            "timestamp": master_ts,
            "profile": "mid_production",
            "statistical_score": 0.1,
            "mahalanobis_score": 0.1,
            "pca_q_score": 0.1,
            "pca_t2_score": 0.1,
            "isolation_forest_score": 0.1,
            "combined_score": 0.5,
            "severity": severity,
            "triggered_detectors": "",
            "affected_variables": "",
            "evidence": "",
        }
    )[_SCORE_COLUMNS]
    scores.to_parquet(anomaly_run / "scores" / "anomaly_scores.parquet", index=False)
    (anomaly_run / "anomaly_fit_manifest.json").write_text(
        json.dumps(
            {
                "fit_window": {"train_end": _TRAIN_END},
                "dataset_fingerprint": {"sha256": "synthetic"},
            }
        ),
        encoding="utf-8",
    )

    forensic_root = tmp_path / "forensics"
    forensic_run = forensic_root / "runs" / "fr1"
    forensic_run.mkdir(parents=True)
    (forensic_run / "forensic_manifest.json").write_text("{}", encoding="utf-8")

    addenda_root = tmp_path / "bom_addenda"
    config = tmp_path / "bom.yaml"
    config.write_text(
        f"""
timeline:
  expected_master_rows: {_N_MASTER}
forensic_windows:
  candidate_dates: ["2024-09-01"]
  window_hours: 24
forensic_addendum:
  enabled: true
  anomaly_root: "{anomaly_root.as_posix()}"
  anomaly_run_id: "chain"
  forensic_root: "{forensic_root.as_posix()}"
  forensic_run_id: "fr1"
  output_root: "{addenda_root.as_posix()}"
""",
        encoding="utf-8",
    )
    return {
        "csv": csv_path,
        "master": master_path,
        "config": config,
        "out_root": tmp_path / "bom_out",
        "addenda_root": addenda_root,
        "master_ts": master_ts,
    }


def test_full_bom_context_chain(world: dict) -> None:
    csv_sha = io.file_sha256(world["csv"])
    master_sha = io.file_sha256(world["master"])

    assert (
        run_bom_context.main(
            [
                "--config",
                str(world["config"]),
                "--csv",
                str(world["csv"]),
                "--master",
                str(world["master"]),
                "--output-root",
                str(world["out_root"]),
                "--run-id",
                "chain",
            ]
        )
        == 0
    )

    out = world["out_root"] / "runs" / "chain"

    # --- manifest is the completion marker and records the contract --------
    manifest = json.loads((out / io.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["completion_status"] == "complete"
    assert manifest["raw_row_count"] == len(_CSV_ROWS)
    assert manifest["rejected_row_count"] == 0
    assert manifest["order_count"] == 4
    assert manifest["master_timeline_row_count"] == _N_MASTER
    assert manifest["overlap_count"] == 1
    assert manifest["gap_count"] == 1
    assert io.resolve_run(world["out_root"], "latest", io.MANIFEST_NAME) == out

    # --- master alignment is exact ------------------------------------------
    timeline = pd.read_parquet(out / io.TIMELINE_FILE)
    assert len(timeline) == _N_MASTER
    assert (timeline["timestamp"].to_numpy() == world["master_ts"].to_numpy()).all()
    statuses = set(timeline["bom_context_status"])
    assert {
        "matched_single_order",
        "transition_overlap",
        "no_active_order",
        "outside_bom_coverage",
    } <= statuses

    # --- overlap policy: both orders preserved, no silent selection ---------
    overlap_rows = timeline[timeline["bom_context_status"] == "transition_overlap"]
    assert (overlap_rows["order_ids"] == "100|101").all()
    assert overlap_rows["order_id"].isna().all()

    # --- transitions cover the crafted scenario -----------------------------
    transitions = pd.read_parquet(out / io.TRANSITIONS_FILE)
    assert {
        "overlap_transition",
        "gap_transition",
        "composition_change",
    } <= set(transitions["transition_type"])

    # --- composition change produced distinct signatures --------------------
    orders = pd.read_parquet(out / io.ORDERS_FILE)
    by_id = orders.set_index("order_id")
    assert by_id.loc["102", "bom_signature"] != by_id.loc["103", "bom_signature"]
    assert by_id.loc["102", "recipe_version"] == by_id.loc["103", "recipe_version"]

    # --- addendum: tables, figures, manifest --------------------------------
    addendum = world["addenda_root"] / "chain"
    addendum_manifest = json.loads(
        (addendum / io.ADDENDUM_MANIFEST_NAME).read_text(encoding="utf-8")
    )
    assert addendum_manifest["completion_status"] == "complete"
    assert addendum_manifest["upstream"]["anomaly_run_id"] == "chain"
    for name in (
        "anomaly_rates_by_product",
        "anomaly_rates_by_recipe",
        "anomaly_rates_by_bom_signature",
        "anomaly_rates_by_order",
        "anomaly_rates_by_context_status",
        "candidate_dates_bom_context",
        "recipe_transition_anomaly_summary",
    ):
        assert (addendum / f"{name}.parquet").exists(), name
        pd.read_parquet(addendum / f"{name}.parquet")  # reloads
    for fig in FIGURES:
        assert (addendum / "figures" / fig).exists(), fig
    assert (addendum / "executive_summary.md").exists()
    assert (addendum / "limitations.md").exists()

    # Validation anomaly concentrates on product 214 in this synthetic world.
    by_product = pd.read_parquet(
        addendum / "anomaly_rates_by_product.parquet"
    ).set_index("product_code")
    assert by_product.loc["214", "anomaly_rate_validation"] == 1.0
    assert by_product.loc["114", "anomaly_rate_validation"] == 0.0

    # --- sources untouched ---------------------------------------------------
    assert io.file_sha256(world["csv"]) == csv_sha
    assert io.file_sha256(world["master"]) == master_sha
