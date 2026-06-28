"""LOG-01 (row-level suppression evidence) + GOV-02 (generic quarantine target).

These exercise the controlled-scoring semantics directly, without a full run:
an unrelated anomaly inside an explained burst window must stay unsuppressed,
and the scenario id / decision text must follow the *proposed* sensor(s) — never
a hardcoded inlet identity.
"""

from __future__ import annotations

import pandas as pd
from src.intelligence.scoring_experiment import decision_report, scenarios, scoring
from src.intelligence.scoring_experiment.quarantine import QuarantineWindow


def _base(
    index: pd.DatetimeIndex,
    severities: list[str],
    affected: list[str],
    faulty: str = "",
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "profile": "high_production",
            "original_severity": severities,
            "original_combined_score": 0.9,
            "affected_variables": affected,
            "sensor_health_context": "",
            "steam_context": "",
            "bom_context_status": "",
            "product_code": "",
            "recipe_context_key": "",
            "faulty_sensors": faulty,
            "quarantine_recommended_sensors": faulty,
        },
        index=index,
    )


# --- LOG-01: row-level evidence gates burst-window suppression --------------


def test_burst_suppression_requires_row_level_evidence() -> None:
    idx = pd.date_range("2024-09-17", periods=12, freq="h")
    severities = ["anomaly"] * 11 + ["normal"]
    # rows 0-9 attributed to the faulty sensor; row 10 is an UNRELATED anomaly
    # (its evidence points elsewhere) inside the same explained window.
    affected = ["inlet_hopper_points|granulator_power"] * 10 + ["material_temp"] + [""]
    base = _base(idx, severities, affected, faulty="inlet_hopper_points")
    window = QuarantineWindow("inlet_hopper_points", idx[0], idx[10])

    out = scoring.apply_quarantine(base, targets=[], burst_windows=[window])

    # Every non-normal row in the window is incident-explained (coverage)...
    assert int(out["incident_explained_for_review"].sum()) == 11
    assert bool(out.iloc[10]["incident_explained_for_review"]) is True
    # ...but only the rows with their OWN evidence are suppressed for review.
    assert int(out["row_suppressed_for_review"].sum()) == 10
    assert bool(out.iloc[10]["row_suppressed_for_review"]) is False
    assert bool(out.iloc[10]["row_level_evidence_match"]) is False
    # The unrelated anomaly keeps its severity; a dominated row is down-ranked.
    assert out.iloc[10]["adjusted_review_severity"] == "anomaly"
    assert out.iloc[0]["adjusted_review_severity"] == "normal"
    assert out.iloc[0]["original_severity"] == "anomaly"


def test_incident_vs_row_columns_are_separate() -> None:
    idx = pd.date_range("2024-09-17", periods=2, freq="h")
    base = _base(idx, ["anomaly", "anomaly"], ["x", "inlet_hopper_points"], faulty="")
    window = QuarantineWindow("inlet_hopper_points", idx[0], idx[1])
    out = scoring.apply_quarantine(base, targets=[], burst_windows=[window])
    # Both incident-explained; only the evidence-bearing row is suppressed.
    assert list(out["incident_explained_for_review"]) == [True, True]
    assert list(out["row_suppressed_for_review"]) == [False, True]
    assert list(out["row_level_evidence_match"]) == [False, True]


# --- GOV-02: scenario id + decision text follow the proposed sensor(s) ------


def test_quarantine_scenario_id_variants() -> None:
    assert scoring.quarantine_scenario_id([]) == ""
    assert (
        scoring.quarantine_scenario_id(["inlet_hopper_points"])
        == "quarantine_inlet_hopper_points_interpretive"
    )
    assert (
        scoring.quarantine_scenario_id(["granulator_roller_gap"])
        == "quarantine_granulator_roller_gap_interpretive"
    )
    assert (
        scoring.quarantine_scenario_id(["sensor_a", "sensor_b"])
        == "quarantine_proposals_interpretive"
    )
    # De-duplicated: one unique sensor -> the single-target id.
    assert (
        scoring.quarantine_scenario_id(["sensor_a", "sensor_a"])
        == "quarantine_sensor_a_interpretive"
    )


def test_sanitize_sensor() -> None:
    assert scoring.sanitize_sensor("sensor-1.x") == "sensor_1_x"
    assert scoring.sanitize_sensor("") == "sensor"


def test_scenario_definitions_reflect_target_sensor() -> None:
    defs = scenarios.scenario_definitions(
        "quarantine_granulator_roller_gap_interpretive", ["granulator_roller_gap"]
    )
    assert "quarantine_granulator_roller_gap_interpretive" in set(defs["scenario_id"])
    assert "inlet_hopper_points" not in defs.to_string()
    quar = defs[
        defs["scenario_id"] == "quarantine_granulator_roller_gap_interpretive"
    ].iloc[0]
    assert "granulator_roller_gap" in quar["description"]


def test_scenario_definitions_no_proposal() -> None:
    defs = scenarios.scenario_definitions("", [])
    assert set(defs["scenario_id"]) == {
        "baseline_v1",
        "healthy_only_proxy",
        "candidate_reference_needed",
    }


def _anomaly_rate(scenario_id: str) -> pd.DataFrame:
    rows = [
        {"scenario_id": "baseline_v1", "suppressed_count": 0, "suppression_rate": 0.0}
    ]
    if scenario_id:
        rows.append(
            {"scenario_id": scenario_id, "suppressed_count": 5, "suppression_rate": 0.5}
        )
    return pd.DataFrame(rows)


def test_decision_report_uses_proposed_sensor() -> None:
    art = decision_report.build_decision_report(
        reference_proposals=pd.DataFrame(),
        reference_quarantine=pd.DataFrame(),
        anomaly_rate=_anomaly_rate("quarantine_granulator_roller_gap_interpretive"),
        recommendations=pd.DataFrame(),
        residual={"material": False},
        run_id="r1",
        upstream_run_ids={"reference": "ref1"},
        quarantine_sensors=["granulator_roller_gap"],
        quarantine_scenario="quarantine_granulator_roller_gap_interpretive",
    )
    actions = set(art.decision_matrix["action"])
    assert "approve_quarantine_granulator_roller_gap" in actions
    assert "approve_quarantine_inlet_hopper_points" not in actions
    assert "inlet_hopper_points" not in art.decision_summary
    assert "granulator_roller_gap" in art.decision_summary
    assert "granulator_roller_gap" in art.required_plant_records.to_string()


def test_decision_report_multiple_targets() -> None:
    art = decision_report.build_decision_report(
        reference_proposals=pd.DataFrame(),
        reference_quarantine=pd.DataFrame(),
        anomaly_rate=_anomaly_rate("quarantine_proposals_interpretive"),
        recommendations=pd.DataFrame(),
        residual={"material": False},
        run_id="r1",
        upstream_run_ids={"reference": "ref1"},
        quarantine_sensors=["sensor_a", "sensor_b"],
        quarantine_scenario="quarantine_proposals_interpretive",
    )
    assert "approve_quarantine_proposed_sensors" in set(art.decision_matrix["action"])
    assert "sensor_a, sensor_b" in art.decision_summary


def test_decision_report_no_proposal() -> None:
    art = decision_report.build_decision_report(
        reference_proposals=pd.DataFrame(),
        reference_quarantine=pd.DataFrame(),
        anomaly_rate=_anomaly_rate(""),
        recommendations=pd.DataFrame(),
        residual={"material": False},
        run_id="r1",
        upstream_run_ids={"reference": "ref1"},
        quarantine_sensors=[],
        quarantine_scenario="",
    )
    assert "inlet_hopper_points" not in art.decision_summary
    assert "No pending quarantine proposal" in art.decision_summary
    approve = art.decision_matrix[
        art.decision_matrix["action"] == "approve_quarantine"
    ].iloc[0]
    assert bool(approve["recommended"]) is False
