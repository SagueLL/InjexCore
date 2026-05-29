"""Build data/features/variable_classification.csv from the dictionary.

Each of the 37 variables is classified into one of four categories
(Control / Process / State / Metadata) and, where applicable, annotated
with a potential ML objective and the corresponding ML task type.

Categories:
  - Control   : operator/controller commands (setpoints, actuator positions,
                SCADA equipment-load registers).
  - Process   : measured physical signals from sensors (temperatures,
                pressures, flows, power draw, production rate, quality).
  - State     : discrete equipment states (running / alarm / direct-drive).
  - Metadata  : identifiers and timestamps (not modeled directly).

ML objectives:
  - anomaly_detection         (unsupervised, multivariate)
  - energy_consumption        (regression)
  - production_rate           (regression)
  - machine_failure           (classification, alarm prediction)
  - temperature_forecasting   (time-series forecasting)
  - pressure_forecasting      (time-series forecasting)
  - product_humidity          (regression, quality)
"""
from __future__ import annotations

import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DICT = PROJECT_ROOT / "data" / "features" / "data_pellets_dictionary.csv"
DST = PROJECT_ROOT / "data" / "features" / "variable_classification.csv"

# (category, primary_objective, ml_type, notes)
CLASSIFICATION: dict[str, tuple[str, str, str, str]] = {
    # --- Metadata ---
    "timestamp":                    ("Metadata", "-",                       "-",             "Time index for all time-series tasks"),
    "work_order":                   ("Metadata", "-",                       "-",             "Identifier; can stratify analyses by order"),
    "deposit_equipment_id":         ("Metadata", "-",                       "-",             "Identifier; equipment routing key"),
    "batch_id":                     ("Metadata", "-",                       "-",             "Identifier; can stratify analyses by batch"),
    "batch_quality_id":             ("Metadata", "-",                       "-",             "Identifier; quality-batch routing key"),

    # --- Control (setpoints + SCADA equipment-load registers + valve command) ---
    "feeder_max_speed_sp":          ("Control",  "-",                       "-",             "Setpoint; input feature for all models"),
    "steam_line_pressure_sp":       ("Control",  "-",                       "-",             "Setpoint; input feature"),
    "granulator_power_sp":          ("Control",  "-",                       "-",             "Setpoint; input feature"),
    "conditioner_temp_sp":          ("Control",  "-",                       "-",             "Setpoint; reference for temp_forecasting residuals"),
    "expander_cone_pressure_sp":    ("Control",  "-",                       "-",             "Setpoint; reference for pressure_forecasting residuals"),
    "granulator_g2_state_pct":      ("Control",  "-",                       "-",             "SCADA load command for granulator"),
    "conditioner_l2_state_pct":     ("Control",  "-",                       "-",             "SCADA load command for conditioner"),
    "feeder_al2_state_pct":         ("Control",  "-",                       "-",             "SCADA load command for feeder"),
    "steam_dosing_valve_me2_pct":   ("Control",  "-",                       "-",             "Valve opening command (manipulated variable)"),

    # --- Process (measured signals) ---
    "conditioner_inlet_temp":       ("Process",  "anomaly_detection",       "unsupervised",  "Inlet thermal condition; baseline for product quality"),
    "granulator_roller_gap":        ("Process",  "anomaly_detection",       "unsupervised",  "Mechanical state; drift indicator for wear"),
    "granulator_power":             ("Process",  "energy_consumption",      "regression",    "Main energy consumer; also anomaly feature"),
    "steam_valve_temp_me2":         ("Process",  "anomaly_detection",       "unsupervised",  "Steam-system thermal signal"),
    "steam_valve_flow_me2":         ("Process",  "anomaly_detection",       "unsupervised",  "Steam mass flow; key process-stability signal"),
    "steam_valve_pressure_me2":     ("Process",  "anomaly_detection",       "unsupervised",  "Steam pressure feedback"),
    "granulator_production_rate":   ("Process",  "production_rate",         "regression",    "Throughput KPI; also energy-efficiency input"),
    "feeder_hopper_temp":           ("Process",  "anomaly_detection",       "unsupervised",  "Upstream thermal condition"),
    "conditioner_l2_power":         ("Process",  "energy_consumption",      "regression",    "Energy draw component"),
    "conditioner_steam_loop_temp":  ("Process",  "temperature_forecasting", "forecasting",   "Controlled temp; lead indicator for thermal upsets"),
    "expander_ex2_power":           ("Process",  "energy_consumption",      "regression",    "Energy draw component"),
    "expander_ex2_hydraulic_press": ("Process",  "pressure_forecasting",    "forecasting",   "Hydraulic state; predictive-maintenance signal"),
    "expander_ex2_outlet_temp":     ("Process",  "temperature_forecasting", "forecasting",   "Product outlet temp; quality-relevant"),
    "extruder_specific_energy":     ("Process",  "energy_consumption",      "regression",    "Primary energy KPI (kWh/t)"),
    "inlet_hopper_humidity":        ("Process",  "product_humidity",        "regression",    "Quality input; affects pellet integrity"),
    "inlet_hopper_points":          ("Process",  "anomaly_detection",       "unsupervised",  "Raw count from new hopper sensor; semantics TBD"),
    "inlet_hopper_temp":            ("Process",  "temperature_forecasting", "forecasting",   "Upstream product temp; pretreatment indicator"),

    # --- State (discrete equipment states) ---
    "granulator_g2_running":        ("State",    "-",                       "-",             "Operating-mode flag; segment data on/off"),
    "granulator_g2_alarm":          ("State",    "machine_failure",         "classification","Primary failure label for granulator"),
    "conditioner_me2_alarm":        ("State",    "machine_failure",         "classification","Primary failure label for conditioner"),
    "conditioner_me2_direct":       ("State",    "-",                       "-",             "Operating-mode flag (direct drive)"),
    "feeder_al2_running":           ("State",    "-",                       "-",             "Operating-mode flag; segment data on/off"),
    "feeder_al2_alarm":             ("State",    "machine_failure",         "classification","Primary failure label for feeder"),
}


def main() -> None:
    if not SRC_DICT.exists():
        raise FileNotFoundError(f"Dictionary not found: {SRC_DICT}. Run build_pellet_dictionary.py first.")

    with SRC_DICT.open("r", encoding="utf-8", newline="") as f:
        dict_rows = list(csv.DictReader(f))

    dict_vars = [r["Variable"] for r in dict_rows]
    missing = [v for v in dict_vars if v not in CLASSIFICATION]
    extra = [v for v in CLASSIFICATION if v not in dict_vars]
    if missing or extra:
        raise ValueError(
            f"Classification / dictionary mismatch.\n"
            f"  Missing from CLASSIFICATION: {missing}\n"
            f"  Extra in CLASSIFICATION:     {extra}"
        )

    out_rows: list[dict[str, str]] = []
    for r in dict_rows:
        variable = r["Variable"]
        category, objective, ml_type, notes = CLASSIFICATION[variable]
        out_rows.append({
            "Variable": variable,
            "Category": category,
            "Unity": r["Unity"],
            "Sensor": r["Sensor"],
            "Potential_Objective": objective,
            "ML_Type": ml_type,
            "Notes": notes,
        })

    DST.parent.mkdir(parents=True, exist_ok=True)
    with DST.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["Variable", "Category", "Unity", "Sensor", "Potential_Objective", "ML_Type", "Notes"],
        )
        writer.writeheader()
        writer.writerows(out_rows)

    counts: dict[str, int] = {}
    for row in out_rows:
        counts[row["Category"]] = counts.get(row["Category"], 0) + 1
    print(f"Wrote {len(out_rows)} rows to {DST}")
    print("Category counts:", counts)


if __name__ == "__main__":
    main()
