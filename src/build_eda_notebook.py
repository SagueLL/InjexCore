"""Generate notebooks/eda_ds_pellet.ipynb from a structured cell list.

The notebook is industrial-focused EDA on data/raw/Dades_pellet.csv:
operating-state segmentation, distributions, time-series overview,
controller tracking, correlations, state-conditioned distributions,
alarm-window analysis, KPI summary. No cosmetics — every plot answers
an operational question.

Re-run to regenerate the notebook; outputs are stripped (committed clean).
"""
from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DST = PROJECT_ROOT / "notebooks" / "eda_ds_pellet.ipynb"


def md(text: str) -> dict:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": text,
    }


def code(text: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": text,
    }


CELLS: list[dict] = [
    md(
        "# EDA — Pellet Granulation Line\n"
        "\n"
        "Industrial-focused EDA on `data/raw/Dades_pellet.csv`. No aesthetics — every plot answers an operational question.\n"
        "\n"
        "**Dataset:** 167,331 rows · 116 days · 1-min cadence (verified clean: `data/features/temporal_quality_report.json`).\n"
        "\n"
        "**Inputs used:**\n"
        "- `data/features/data_pellets_dictionary.csv` — variable inventory\n"
        "- `data/features/variable_classification.csv` — Control / Process / State / Metadata\n"
        "\n"
        "**Sections:**\n"
        "1. Setup & loading (multi-row header, decimal-comma)\n"
        "2. Operating-state overview (filter idle before stats)\n"
        "3. Distributions of process variables\n"
        "4. Time series — process signals over 116 days\n"
        "5. Controller tracking (SP vs PV)\n"
        "6. Correlations\n"
        "7. State-conditioned distributions (active vs idle)\n"
        "8. Alarm-window analysis\n"
        "9. KPI summary (specific energy, throughput)\n"
        "10. Findings checklist\n"
    ),

    md("## 1. Setup & loading"),

    code(
        "from pathlib import Path\n"
        "\n"
        "import numpy as np\n"
        "import pandas as pd\n"
        "import matplotlib.pyplot as plt\n"
        "import seaborn as sns\n"
        "\n"
        "pd.set_option('display.max_columns', 50)\n"
        "pd.set_option('display.width', 160)\n"
        "sns.set_theme(context='notebook', style='whitegrid')\n"
        "\n"
        "RAW = Path('../data/raw/Dades_pellet.csv')\n"
        "DICT_PATH = Path('../data/features/data_pellets_dictionary.csv')\n"
        "CLF_PATH = Path('../data/features/variable_classification.csv')\n"
    ),

    code(
        "# Source CSV has 3 header rows: row0 = description, row1 = PLC code, row2 = unit.\n"
        "# Decimal separator is ',' and encoding is latin-1.\n"
        "header = pd.read_csv(RAW, nrows=3, header=None, encoding='latin-1')\n"
        "codes = header.iloc[1].astype(str).tolist()\n"
        "\n"
        "df = pd.read_csv(\n"
        "    RAW,\n"
        "    skiprows=3,\n"
        "    header=None,\n"
        "    names=codes,\n"
        "    decimal=',',\n"
        "    encoding='latin-1',\n"
        "    low_memory=False,\n"
        ")\n"
        "df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce')\n"
        "df = df.dropna(subset=['Fecha']).set_index('Fecha').sort_index()\n"
        "df.index.name = 'timestamp'\n"
        "df.shape\n"
    ),

    code(
        "# Rename PLC codes to logical variable names via the dictionary.\n"
        "dict_df = pd.read_csv(DICT_PATH)\n"
        "clf = pd.read_csv(CLF_PATH).set_index('Variable')\n"
        "\n"
        "rename_map = dict(zip(dict_df['Sensor'], dict_df['Variable']))\n"
        "df = df.rename(columns=rename_map)\n"
        "\n"
        "# Force numeric on every non-metadata column.\n"
        "metadata_vars = [v for v in clf[clf['Category'] == 'Metadata'].index if v != 'timestamp']\n"
        "for c in df.columns:\n"
        "    if c not in metadata_vars:\n"
        "        df[c] = pd.to_numeric(df[c], errors='coerce')\n"
        "\n"
        "df.dtypes.value_counts()\n"
    ),

    code(
        "# Variable groups (intersect with what is actually present).\n"
        "process_vars = [v for v in clf[clf['Category'] == 'Process'].index if v in df.columns]\n"
        "control_vars = [v for v in clf[clf['Category'] == 'Control'].index if v in df.columns]\n"
        "state_vars   = [v for v in clf[clf['Category'] == 'State'].index   if v in df.columns]\n"
        "print(f'Process: {len(process_vars)} | Control: {len(control_vars)} | State: {len(state_vars)}')\n"
        "df.head(3)\n"
    ),

    md(
        "## 2. Operating-state overview\n"
        "\n"
        "Filter idle rows *before* computing stats — production-off periods sit at zero across most signals and would otherwise dominate distributions and correlations.\n"
    ),

    code(
        "# Fraction of rows where each binary flag is 1.\n"
        "state_pct = (df[state_vars].mean() * 100).round(2).sort_values(ascending=False)\n"
        "state_pct\n"
    ),

    code(
        "# 'Active' = any of the three running flags is 1.\n"
        "running_flags = [c for c in state_vars if c.endswith('_running')]\n"
        "df['is_active'] = df[running_flags].any(axis=1).astype(int)\n"
        "active_pct = df['is_active'].mean() * 100\n"
        "print(f'Active fraction: {active_pct:.2f}%')\n"
        "print(f'Active rows:     {int(df[\"is_active\"].sum()):,} / {len(df):,}')\n"
    ),

    code(
        "# Daily active fraction — visualises production cadence over the 116 days.\n"
        "daily_active = df['is_active'].resample('1D').mean()\n"
        "fig, ax = plt.subplots(figsize=(14, 3))\n"
        "daily_active.plot(ax=ax, lw=1)\n"
        "ax.set_ylabel('Daily active fraction')\n"
        "ax.set_title('Production activity over time')\n"
        "ax.set_ylim(0, 1.05); ax.grid(True, alpha=0.3)\n"
        "plt.tight_layout(); plt.show()\n"
    ),

    code(
        "# Alarm minutes per day per equipment.\n"
        "alarm_flags = [c for c in state_vars if c.endswith('_alarm')]\n"
        "alarm_daily = df[alarm_flags].resample('1D').sum()\n"
        "ax = alarm_daily.plot(figsize=(14, 4), title='Alarm minutes per day', grid=True, alpha=0.8)\n"
        "ax.set_ylabel('Minutes in alarm')\n"
        "plt.tight_layout(); plt.show()\n"
        "print('Total alarm minutes per equipment:')\n"
        "print(df[alarm_flags].sum())\n"
    ),

    md("## 3. Distributions — process variables (active rows only)"),

    code(
        "active = df[df['is_active'] == 1]\n"
        "active[process_vars].hist(figsize=(20, 15), bins=60, color='steelblue', edgecolor='white')\n"
        "plt.suptitle('Process variable distributions (active production rows)', y=1.0, fontsize=14)\n"
        "plt.tight_layout(); plt.show()\n"
    ),

    code(
        "# Stability ranking: coefficient of variation. High CV -> intermittent / multi-mode.\n"
        "desc = active[process_vars].describe().T\n"
        "desc['cv'] = (desc['std'] / desc['mean'].replace(0, np.nan)).abs()\n"
        "desc[['mean', 'std', 'min', 'max', 'cv']].sort_values('cv', ascending=False).round(3)\n"
    ),

    md(
        "**Reading the table above:**\n"
        "- Very low CV (< 0.05) → tightly controlled signal; controller is in regulation.\n"
        "- Very high CV (> 0.5) → highly intermittent or operating across multiple regimes; check the histogram for bimodality.\n"
        "- Bimodal distributions usually mean two distinct operating modes — cluster before training.\n"
    ),

    md("## 4. Time series — process signals (downsampled to 5 min)"),

    code(
        "# Downsample for plotting; full 167k samples are unreadable on a single plot.\n"
        "df_5m = df[process_vars].resample('5min').mean()\n"
        "n = len(process_vars)\n"
        "fig, axes = plt.subplots(n, 1, figsize=(16, 1.8 * n), sharex=True)\n"
        "for ax, col in zip(axes, process_vars):\n"
        "    df_5m[col].plot(ax=ax, lw=0.7, color='steelblue')\n"
        "    ax.set_ylabel(col, fontsize=8, rotation=0, ha='right', va='center')\n"
        "    ax.grid(True, alpha=0.3)\n"
        "axes[-1].set_xlabel('time')\n"
        "fig.suptitle('Process variables — 5-min mean across the full record', y=1.0, fontsize=12)\n"
        "plt.tight_layout(); plt.show()\n"
    ),

    md(
        "## 5. Controller tracking — setpoint vs measurement\n"
        "\n"
        "For each setpoint, compare against the closest physical measurement. Sustained tracking error → controller saturation, manual override, or sensor drift. Spikes → upset events.\n"
    ),

    code(
        "# SP -> PV mapping (domain-informed; refine if a real mapping doc emerges).\n"
        "pairs = [\n"
        "    ('conditioner_temp_sp',        'conditioner_steam_loop_temp',   'Conditioner temp'),\n"
        "    ('steam_line_pressure_sp',     'steam_valve_pressure_me2',      'Steam line pressure'),\n"
        "    ('expander_cone_pressure_sp',  'expander_ex2_hydraulic_press',  'Expander cone pressure'),\n"
        "    ('granulator_power_sp',        'granulator_power',              'Granulator power'),\n"
        "]\n"
        "fig, axes = plt.subplots(len(pairs), 1, figsize=(15, 3 * len(pairs)), sharex=True)\n"
        "for ax, (sp, pv, title) in zip(axes, pairs):\n"
        "    d = df[[sp, pv]].resample('15min').mean()\n"
        "    d[sp].plot(ax=ax, color='red',       lw=1.1, alpha=0.7, label='SP (setpoint)')\n"
        "    d[pv].plot(ax=ax, color='steelblue', lw=0.8,            label='PV (measurement)')\n"
        "    ax.set_title(title); ax.legend(loc='upper right'); ax.grid(True, alpha=0.3)\n"
        "plt.tight_layout(); plt.show()\n"
    ),

    code(
        "# Tracking error stats during active production.\n"
        "err = pd.DataFrame({f'{pv}__minus__{sp}': active[pv] - active[sp] for sp, pv, _ in pairs})\n"
        "err.describe().T[['mean', 'std', 'min', 'max']].round(3)\n"
    ),

    md("## 6. Correlations — process + control variables (active rows)"),

    code(
        "numeric_vars = process_vars + control_vars\n"
        "corr = active[numeric_vars].corr()\n"
        "fig, ax = plt.subplots(figsize=(14, 12))\n"
        "sns.heatmap(\n"
        "    corr,\n"
        "    cmap='RdBu_r', center=0, vmin=-1, vmax=1,\n"
        "    square=True, linewidths=0.3,\n"
        "    cbar_kws={'shrink': 0.7, 'label': 'Pearson r'},\n"
        "    ax=ax,\n"
        ")\n"
        "ax.set_title('Pearson correlations — Process + Control (active rows)')\n"
        "plt.tight_layout(); plt.show()\n"
    ),

    code(
        "# Top 20 absolute correlations (no self-pairs, no mirrored duplicates).\n"
        "# Filter a != b inline instead of mutating the diagonal (pandas 3.x returns read-only arrays).\n"
        "pairs_seen, rows = set(), []\n"
        "for (a, b), v in corr.abs().stack().sort_values(ascending=False).items():\n"
        "    if a == b or (b, a) in pairs_seen:\n"
        "        continue\n"
        "    pairs_seen.add((a, b))\n"
        "    rows.append({'var_a': a, 'var_b': b, 'r': round(corr.loc[a, b], 3)})\n"
        "pd.DataFrame(rows).head(20)\n"
    ),

    md(
        "## 7. State-conditioned distributions — active vs idle\n"
        "\n"
        "Quantifies how strongly each signal moves with production. Signals with overlapping active/idle distributions are weak production indicators; signals with cleanly separated distributions are strong ones.\n"
    ),

    code(
        "key = [\n"
        "    'granulator_power', 'expander_ex2_outlet_temp', 'conditioner_steam_loop_temp',\n"
        "    'extruder_specific_energy', 'granulator_production_rate', 'steam_valve_flow_me2',\n"
        "]\n"
        "fig, axes = plt.subplots(2, 3, figsize=(16, 8))\n"
        "for ax, col in zip(axes.flat, key):\n"
        "    df[df['is_active'] == 1][col].plot.hist(bins=50, alpha=0.6, ax=ax, label='active', color='steelblue')\n"
        "    df[df['is_active'] == 0][col].plot.hist(bins=50, alpha=0.6, ax=ax, label='idle',   color='gray')\n"
        "    ax.set_title(col, fontsize=10); ax.legend()\n"
        "plt.tight_layout(); plt.show()\n"
    ),

    md(
        "## 8. Alarm windows\n"
        "\n"
        "Plot normalized signals around the first alarm onset for each equipment. Leading patterns (signal moves before the flag) are candidates for predictive-maintenance features.\n"
    ),

    code(
        "# Detect rising edges per alarm flag.\n"
        "onsets = {}\n"
        "for a in alarm_flags:\n"
        "    diff = df[a].astype(int).diff().fillna(0)\n"
        "    onsets[a] = df.index[diff == 1].tolist()\n"
        "{a: len(t) for a, t in onsets.items()}\n"
    ),

    code(
        "key_signals = [\n"
        "    'granulator_power', 'granulator_production_rate',\n"
        "    'steam_valve_pressure_me2', 'expander_ex2_outlet_temp',\n"
        "    'conditioner_steam_loop_temp',\n"
        "]\n"
        "\n"
        "def plot_alarm_window(flag, signals, halfwin_min=30):\n"
        "    if not onsets.get(flag):\n"
        "        print(f'No {flag} onsets detected.')\n"
        "        return\n"
        "    t0 = onsets[flag][0]\n"
        "    w = df.loc[t0 - pd.Timedelta(minutes=halfwin_min) : t0 + pd.Timedelta(minutes=halfwin_min), signals]\n"
        "    if w.empty:\n"
        "        print(f'No data around {t0} for {flag}.')\n"
        "        return\n"
        "    fig, ax = plt.subplots(figsize=(14, 5))\n"
        "    for c in w.columns:\n"
        "        norm = (w[c] - w[c].min()) / (w[c].max() - w[c].min() + 1e-9)\n"
        "        norm.plot(ax=ax, label=c, lw=1)\n"
        "    ax.axvline(t0, color='red', linestyle='--', label=f'{flag} onset')\n"
        "    ax.legend(loc='center left', bbox_to_anchor=(1.0, 0.5))\n"
        "    ax.set_title(f'Normalized signals +/- {halfwin_min} min around first {flag}')\n"
        "    ax.grid(True, alpha=0.3)\n"
        "    plt.tight_layout(); plt.show()\n"
        "\n"
        "for f in alarm_flags:\n"
        "    plot_alarm_window(f, key_signals)\n"
    ),

    md("## 9. KPI summary — specific energy & throughput"),

    code(
        "active_only = df[df['is_active'] == 1]\n"
        "print('Specific energy (kWh/t) — active periods:')\n"
        "print(active_only['extruder_specific_energy'].describe().round(3))\n"
        "print()\n"
        "print('Production rate (kg/min) — active periods:')\n"
        "print(active_only['granulator_production_rate'].describe().round(3))\n"
        "\n"
        "fig, axes = plt.subplots(1, 2, figsize=(15, 4))\n"
        "active_only['extruder_specific_energy'].resample('1H').mean().plot(\n"
        "    ax=axes[0], title='Hourly specific energy (kWh/t)', lw=0.8)\n"
        "active_only['granulator_production_rate'].resample('1H').mean().plot(\n"
        "    ax=axes[1], title='Hourly production rate (kg/min)', lw=0.8)\n"
        "for a in axes:\n"
        "    a.grid(True, alpha=0.3); a.set_xlabel('time')\n"
        "plt.tight_layout(); plt.show()\n"
    ),

    code(
        "# Energy-vs-throughput scatter — operating-point view.\n"
        "fig, ax = plt.subplots(figsize=(8, 6))\n"
        "ax.scatter(\n"
        "    active_only['granulator_production_rate'],\n"
        "    active_only['extruder_specific_energy'],\n"
        "    s=2, alpha=0.15, color='steelblue',\n"
        ")\n"
        "ax.set_xlabel('Production rate (kg/min)')\n"
        "ax.set_ylabel('Specific energy (kWh/t)')\n"
        "ax.set_title('Operating points — active rows')\n"
        "ax.grid(True, alpha=0.3)\n"
        "plt.tight_layout(); plt.show()\n"
    ),

    md(
        "## 10. Findings checklist\n"
        "\n"
        "Populate after running the notebook end-to-end. Items in italics are the questions to answer — replace with observed values.\n"
        "\n"
        "- **Active fraction (production-on time):** _ %_\n"
        "- **Tightest-tracking control loop (lowest tracking-error std):** _ _\n"
        "- **Worst-tracking control loop:** _ _\n"
        "- **Strongest positive correlation pair:** _ _\n"
        "- **Strongest negative correlation pair:** _ _\n"
        "- **Most bimodal process variable (multiple regimes):** _ _\n"
        "- **Variable with highest CV (most variable):** _ _\n"
        "- **Alarms with clear leading signals (predictive-maintenance candidates):** _ _\n"
        "- **Idle-period contamination risk:** ALL regressions and anomaly models should filter `is_active==1`.\n"
        "- **Next steps:** baseline a classifier on alarm flags using the active-row subset; train an unsupervised anomaly detector on the Process+Control matrix; forecast `expander_ex2_outlet_temp` as a leading thermal indicator.\n"
    ),
]


NOTEBOOK = {
    "cells": CELLS,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3.14",
            "language": "python",
            "name": "python3",
        },
        "language_info": {
            "name": "python",
            "version": "3.14",
            "mimetype": "text/x-python",
            "codemirror_mode": {"name": "ipython", "version": 3},
            "pygments_lexer": "ipython3",
            "nbconvert_exporter": "python",
            "file_extension": ".py",
        },
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}


def main() -> None:
    DST.parent.mkdir(parents=True, exist_ok=True)
    with DST.open("w", encoding="utf-8") as f:
        json.dump(NOTEBOOK, f, indent=1, ensure_ascii=False)
    n_md = sum(1 for c in CELLS if c["cell_type"] == "markdown")
    n_code = sum(1 for c in CELLS if c["cell_type"] == "code")
    print(f"Wrote {DST}")
    print(f"  {n_md} markdown cells, {n_code} code cells, {len(CELLS)} total")


if __name__ == "__main__":
    main()
