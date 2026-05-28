"""Cross-signal contradiction detection (detect-only).

Five rules from the plan:
1. Granulator off but production_rate > min_production_kgmin.
2. Granulator on but power < min_power_pct.
3. Alarm off but any temperature column > hot_temperature_threshold_c.
4. Alarm on, running stays 0 longer than alarm_shutdown_window_min.
5. |SP - PV| / SP > sp_pv_max_drift_pct / 100 sustained for > drift_min.

``apply`` is a no-op so the orchestrator can call every module uniformly.
"""
from __future__ import annotations

import pandas as pd

from src.data.cleaning.column_groups import ColumnGroups
from src.data.cleaning.policy import CleaningPolicy
from src.data.cleaning.reporting import Finding, Severity

# (alarm, running) pairs implied by the running_flags / alarm_flags lists.
_ALARM_RUNNING_PAIRS = (
    ("granulator_g2_alarm", "granulator_g2_running"),
    ("feeder_al2_alarm", "feeder_al2_running"),
    ("conditioner_me2_alarm", "conditioner_me2_direct"),
)

# Setpoint ↔ PV pairs (feeder_max_speed_sp has no clear PV; skipped).
_SP_PV_PAIRS = (
    ("conditioner_temp_sp", "conditioner_inlet_temp"),
    ("steam_line_pressure_sp", "steam_valve_pressure_me2"),
    ("granulator_power_sp", "granulator_power"),
    ("expander_cone_pressure_sp", "extruder_specific_energy"),
)


def detect(
    df: pd.DataFrame,
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> list[Finding]:
    findings: list[Finding] = []
    findings.extend(_rule_off_with_production(df, policy))
    findings.extend(_rule_on_with_low_power(df, policy))
    findings.extend(_rule_alarm_off_but_hot(df, policy, groups))
    findings.extend(_rule_alarm_persistent_run(df, policy))
    findings.extend(_rule_sp_pv_drift(df, policy))
    return findings


def apply(
    df: pd.DataFrame,
    findings: list[Finding],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> pd.DataFrame:
    return df


def _rule_off_with_production(
    df: pd.DataFrame, policy: CleaningPolicy,
) -> list[Finding]:
    cols = {"granulator_g2_running", "granulator_production_rate"}
    if not cols.issubset(df.columns):
        return []
    mask = (df["granulator_g2_running"].fillna(1) == 0) & (
        df["granulator_production_rate"].fillna(0)
        > policy.state_consistency.min_production_kgmin
    )
    return _row_finding(mask, "off_with_production", "granulator_production_rate")


def _rule_on_with_low_power(
    df: pd.DataFrame, policy: CleaningPolicy,
) -> list[Finding]:
    cols = {"granulator_g2_running", "granulator_power"}
    if not cols.issubset(df.columns):
        return []
    mask = (df["granulator_g2_running"].fillna(0) == 1) & (
        df["granulator_power"].fillna(100)
        < policy.state_consistency.min_power_pct
    )
    return _row_finding(mask, "on_with_low_power", "granulator_power")


def _rule_alarm_off_but_hot(
    df: pd.DataFrame, policy: CleaningPolicy, groups: ColumnGroups,
) -> list[Finding]:
    alarm_cols = [c for c in groups.alarm_flags if c in df.columns]
    temp_cols = [c for c in groups.temperature_cols if c in df.columns]
    if not alarm_cols or not temp_cols:
        return []
    any_alarm = df[alarm_cols].fillna(0).sum(axis=1) > 0
    hot = (df[temp_cols] > policy.state_consistency.hot_temperature_threshold_c).any(axis=1)
    mask = (~any_alarm) & hot
    return _row_finding(mask, "alarm_off_but_hot", column=None)


def _rule_alarm_persistent_run(
    df: pd.DataFrame, policy: CleaningPolicy,
) -> list[Finding]:
    findings: list[Finding] = []
    window = policy.state_consistency.alarm_shutdown_window_min
    for alarm_col, running_col in _ALARM_RUNNING_PAIRS:
        if alarm_col not in df.columns or running_col not in df.columns:
            continue
        findings.extend(_alarm_persistent_for_pair(df, alarm_col, running_col, window))
    return findings


def _alarm_persistent_for_pair(
    df: pd.DataFrame, alarm_col: str, running_col: str, window: int,
) -> list[Finding]:
    alarm = df[alarm_col].fillna(0).to_numpy()
    running = df[running_col].fillna(0).to_numpy()
    findings: list[Finding] = []
    n = len(df)
    i = 0
    while i < n:
        if alarm[i] != 1:
            i += 1
            continue
        j = i
        off_after = 0
        while j < n and alarm[j] == 1:
            if running[j] == 0:
                off_after += 1
            j += 1
        if off_after > window:
            findings.append(Finding(
                check="state_consistency",
                severity=Severity.AWARE,
                finding_type="alarm_with_extended_shutdown",
                column=alarm_col,
                row_range=(int(i), int(j - 1)),
                count=off_after,
                action_taken="tag_only",
                evidence={"running_col": running_col, "off_minutes": off_after},
            ))
        i = j
    return findings


def _rule_sp_pv_drift(
    df: pd.DataFrame, policy: CleaningPolicy,
) -> list[Finding]:
    findings: list[Finding] = []
    threshold = policy.state_consistency.sp_pv_max_drift_pct / 100.0
    min_run = policy.state_consistency.sp_pv_drift_min_minutes
    for sp_col, pv_col in _SP_PV_PAIRS:
        if sp_col not in df.columns or pv_col not in df.columns:
            continue
        findings.extend(_sp_pv_for_pair(df, sp_col, pv_col, threshold, min_run))
    return findings


def _sp_pv_for_pair(
    df: pd.DataFrame, sp_col: str, pv_col: str, threshold: float, min_run: int,
) -> list[Finding]:
    sp = df[sp_col]
    pv = df[pv_col]
    valid = sp.notna() & pv.notna() & (sp.abs() > 1e-9)
    drift_ratio = (sp - pv).abs() / sp.abs().replace(0, pd.NA)
    over = (drift_ratio > threshold) & valid
    return _run_findings(over, "sp_pv_drift", sp_col, min_run, evidence_extra={"pv_col": pv_col})


def _row_finding(
    mask: pd.Series, finding_type: str, column: str | None,
) -> list[Finding]:
    if not mask.any():
        return []
    rows = [int(i) for i in mask[mask].index.tolist()]
    return [Finding(
        check="state_consistency",
        severity=Severity.IMPORTANT,
        finding_type=finding_type,
        column=column,
        row_range=(rows[0], rows[-1]),
        count=len(rows),
        action_taken="tag_only",
        evidence={"rows": rows[:50]},
    )]


def _run_findings(
    mask: pd.Series,
    finding_type: str,
    column: str,
    min_run: int,
    evidence_extra: dict[str, object] | None = None,
) -> list[Finding]:
    findings: list[Finding] = []
    arr = mask.fillna(False).to_numpy()
    idx = mask.index.to_numpy()
    n = len(arr)
    i = 0
    while i < n:
        if not arr[i]:
            i += 1
            continue
        j = i
        while j < n and arr[j]:
            j += 1
        run_len = j - i
        if run_len > min_run:
            ev: dict[str, object] = {"length": int(run_len)}
            if evidence_extra:
                ev.update(evidence_extra)
            findings.append(Finding(
                check="state_consistency",
                severity=Severity.AWARE,
                finding_type=finding_type,
                column=column,
                row_range=(int(idx[i]), int(idx[j - 1])),
                count=int(run_len),
                action_taken="tag_only",
                evidence=ev,
            ))
        i = j
    return findings
