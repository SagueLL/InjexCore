"""Curated sensor display names (API contract §6 — 17-entry registry).

Human-readable names for the monitored sensor channels served by the
sensor-health view. Curated copy, backend-served (contract Decision 2).
"""

from __future__ import annotations

SENSOR_DISPLAY_NAMES: dict[str, str] = {
    "conditioner_inlet_temp": "Conditioner inlet temperature",
    "conditioner_l2_power": "Conditioner L2 power",
    "conditioner_steam_loop_temp": "Conditioner steam loop temperature",
    "expander_ex2_hydraulic_press": "Expander EX2 hydraulic pressure",
    "expander_ex2_outlet_temp": "Expander EX2 outlet temperature",
    "expander_ex2_power": "Expander EX2 power",
    "extruder_specific_energy": "Extruder specific energy",
    "feeder_hopper_temp": "Feeder hopper temperature",
    "granulator_power": "Granulator power",
    "granulator_production_rate": "Granulator production rate",
    "granulator_roller_gap": "Granulator roller gap",
    "inlet_hopper_humidity": "Inlet hopper humidity",
    "inlet_hopper_points": "Inlet hopper points counter",
    "inlet_hopper_temp": "Inlet hopper temperature",
    "steam_valve_flow_me2": "Steam valve flow ME2",
    "steam_valve_pressure_me2": "Steam valve pressure ME2",
    "steam_valve_temp_me2": "Steam valve temperature ME2",
}


def display_name_for(sensor_id: str) -> str:
    """Registry lookup with a readable fallback so new sensors never fail."""
    fallback = sensor_id.replace("_", " ").capitalize()
    return SENSOR_DISPLAY_NAMES.get(sensor_id, fallback)
