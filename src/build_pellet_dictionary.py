"""Build the variable inventory (data dictionary) for data/raw/Dades_pellet.csv.

Reads the multi-row header of the source CSV (row 0 = Spanish description,
row 1 = PLC tag code, row 2 = unit) and emits
data/features/data_pellets_dictionary.csv with one row per variable.

Sampling rate inferred from timestamp deltas: 1 row per minute (60s).
"""
from __future__ import annotations

import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "data" / "raw" / "Dades_pellet.csv"
DST = PROJECT_ROOT / "data" / "features" / "data_pellets_dictionary.csv"

# --- Per-column metadata: (variable, type, description_en, critical) ---
# Keyed by column index (0..36). Unit and sensor (PLC tag) come from the CSV header.
COLUMN_META: dict[int, tuple[str, str, str, str]] = {
    0:  ("timestamp",                    "datetime",    "Acquisition timestamp",                                                           "high"),
    1:  ("work_order",                   "categorical", "Production work order ID",                                                        "low"),
    2:  ("deposit_equipment_id",         "categorical", "Source deposit / equipment identifier",                                           "low"),
    3:  ("batch_id",                     "categorical", "Production batch ID",                                                             "low"),
    4:  ("batch_quality_id",             "categorical", "Quality batch identifier (Lote_id&2)",                                            "low"),
    5:  ("feeder_max_speed_sp",          "float",       "Setpoint: feeder maximum speed in working phase",                                 "medium"),
    6:  ("steam_line_pressure_sp",       "float",       "Setpoint: steam line pressure",                                                   "medium"),
    7:  ("granulator_power_sp",          "float",       "Setpoint: granulator power in working phase",                                     "medium"),
    8:  ("conditioner_temp_sp",          "float",       "Setpoint: conditioner temperature",                                               "medium"),
    9:  ("expander_cone_pressure_sp",    "float",       "Setpoint: expander cone pressure",                                                "medium"),
    10: ("conditioner_inlet_temp",       "float",       "Conditioner L-2 inlet product temperature (sensor 4)",                            "high"),
    11: ("granulator_roller_gap",        "float",       "Granulator G2 roller separation distance",                                        "medium"),
    12: ("granulator_power",             "float",       "Granulator G2 motor power (motors A and B)",                                      "high"),
    13: ("steam_valve_temp_me2",         "float",       "Steam temperature at ME2 pressure-regulating valve to conditioner",               "high"),
    14: ("steam_valve_flow_me2",         "float",       "Steam mass flow through ME2 dosing valve to conditioner",                         "high"),
    15: ("steam_valve_pressure_me2",     "float",       "Steam pressure at ME2 pressure-regulating valve to conditioner",                  "high"),
    16: ("granulator_production_rate",   "float",       "Granulator G2 instantaneous production rate",                                     "high"),
    17: ("granulator_g2_state_pct",      "float",       "Granulator G2 SCADA auxiliary state register",                                    "medium"),
    18: ("granulator_g2_running",        "bool",        "Granulator G2 motor running flag",                                                "high"),
    19: ("granulator_g2_alarm",          "bool",        "Granulator G2 alarm flag",                                                        "high"),
    20: ("conditioner_l2_state_pct",     "float",       "Conditioner L-2 SCADA auxiliary state register",                                  "medium"),
    21: ("conditioner_me2_alarm",        "bool",        "Conditioner L-2 (ME2) alarm flag",                                                "high"),
    22: ("conditioner_me2_direct",       "bool",        "Conditioner L-2 (ME2) direct-drive state flag",                                   "medium"),
    23: ("feeder_hopper_temp",           "float",       "Feeder hopper temperature, granulation line L-2 (0-150 C)",                       "high"),
    24: ("conditioner_l2_power",         "float",       "Conditioner L-2 power",                                                           "medium"),
    25: ("conditioner_steam_loop_temp",  "float",       "Conditioner L-2 steam control-loop temperature (sensor 1)",                       "high"),
    26: ("expander_ex2_power",           "float",       "Expander EX2 power",                                                              "medium"),
    27: ("expander_ex2_hydraulic_press", "float",       "Expander EX2 hydraulic group cone pressure",                                      "high"),
    28: ("feeder_al2_state_pct",         "float",       "Feeder AL2 SCADA auxiliary state register",                                       "medium"),
    29: ("feeder_al2_running",           "bool",        "Feeder AL2 running flag",                                                         "high"),
    30: ("feeder_al2_alarm",             "bool",        "Feeder AL2 alarm flag",                                                           "high"),
    31: ("steam_dosing_valve_me2_pct",   "float",       "Steam dosing valve ME2 opening percentage",                                       "medium"),
    32: ("expander_ex2_outlet_temp",     "float",       "Expander EX2 outlet product temperature (sensor 1)",                              "high"),
    33: ("extruder_specific_energy",     "float",       "Extruder specific energy consumption (Kwh per tonne)",                            "high"),
    34: ("inlet_hopper_humidity",        "float",       "Inlet hopper material humidity (NEW)",                                            "high"),
    35: ("inlet_hopper_points",          "float",       "Inlet hopper sensor reading in 'points' (NEW, unitless raw count)",               "medium"),
    36: ("inlet_hopper_temp",            "float",       "Inlet hopper material temperature (NEW)",                                         "high"),
}

UNIT_NORMALIZE = {
    "": "-",
    "ºC": "C",
    "�C": "C",
    "Binari (0/1)": "0/1",
    "State": "0/1",
    "Kg/h": "kg/h",
    "Kg/min": "kg/min",
    "Kwh/T": "kWh/t",
}


def normalize_unit(raw: str) -> str:
    raw = (raw or "").strip()
    return UNIT_NORMALIZE.get(raw, raw)


def main() -> None:
    with SRC.open("r", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        header_rows = [next(reader) for _ in range(3)]

    descriptions_es, codes, units = header_rows
    n_cols = len(codes)
    assert n_cols == 37, f"Expected 37 columns, got {n_cols}"

    rows_out: list[dict[str, str]] = []
    for i in range(n_cols):
        variable, vtype, desc_en, critical = COLUMN_META[i]
        sensor = codes[i].strip()
        unit = normalize_unit(units[i])
        rows_out.append({
            "Variable": variable,
            "Type": vtype,
            "Unity": unit,
            "Sensor": sensor,
            "Frequency": "1min",
            "Critical": critical,
            "Description": desc_en,
        })

    DST.parent.mkdir(parents=True, exist_ok=True)
    with DST.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["Variable", "Type", "Unity", "Sensor", "Frequency", "Critical", "Description"],
        )
        writer.writeheader()
        writer.writerows(rows_out)

    print(f"Wrote {len(rows_out)} rows to {DST}")


if __name__ == "__main__":
    main()
