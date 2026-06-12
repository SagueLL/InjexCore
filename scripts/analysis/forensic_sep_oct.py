"""Read-only forensic analysis of the September-October validation shift.

Consumes the verified, persisted Intelligence-Layer artifacts (behaviour,
correlation run 20260611T171504Z, pca run 20260611T172019Z, anomaly run
20260611T173316Z) plus raw sensor values from the master dataset, and writes
a run-versioned forensic report to ``data/intelligence/forensics/runs/<id>/``.

Strictly read-only with respect to upstream artifacts: no fit procedure is
invoked, no thresholds recomputed, nothing upstream modified. The forensic
manifest is written last (completion marker) via ``--finalize``, after the
executive summary has been reviewed and added.

Usage::

    python scripts/analysis/forensic_sep_oct.py                # run analysis
    python scripts/analysis/forensic_sep_oct.py --finalize ID  # write manifest
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
from scipy import stats
from src.config import DATASETS_DIR, INTELLIGENCE_DIR
from src.intelligence._common.runs import new_run_id, run_dir

log = logging.getLogger("forensic_sep_oct")

# Verified upstream runs (overridable via CLI).
CORR_RUN_ID = "20260611T171504Z"
PCA_RUN_ID = "20260611T172019Z"
ANOM_RUN_ID = "20260611T173316Z"

MASTER_PATH = DATASETS_DIR / "master" / "master_dataset.parquet"
BEHAVIOUR_DIR = INTELLIGENCE_DIR / "behaviour"
FORENSICS_ROOT = INTELLIGENCE_DIR / "forensics"

DETECTORS = ["statistical", "mahalanobis", "pca_q", "pca_t2", "isolation_forest"]
STEAM_SENSORS = [
    "steam_valve_temp_me2",
    "conditioner_steam_loop_temp",
    "steam_valve_pressure_me2",
]
OCT_START = pd.Timestamp("2024-10-01")

# Sustained-deviation rule (stated in every output that uses it): first day
# whose anomaly-severity rate exceeds SUSTAINED_THR and that starts a run of
# at least SUSTAINED_DAYS consecutive such days. Train-window daily rate is
# ~1.1% by construction (p99/p99.9 severity percentiles), so 10% is ~9x the
# fitted baseline. Sensitivity at 25% and 50% is reported alongside.
SUSTAINED_THR = 0.10
SUSTAINED_DAYS = 3
SENSITIVITY_THRS = [0.25, 0.50]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _p95(s: pd.Series) -> float:
    return float(s.quantile(0.95))


# --------------------------------------------------------------------------
# Phase 0 — artifact-discovery gate
# --------------------------------------------------------------------------


def load_and_gate(corr_dir: Path, pca_dir: Path, anom_dir: Path) -> dict[str, Any]:
    """Load manifests, assert cross-component alignment, return shared facts."""
    behaviour_man = _read_json(BEHAVIOUR_DIR / "behaviour_fit_manifest.json")
    corr_man = _read_json(corr_dir / "correlation_fit_manifest.json")
    pca_man = _read_json(pca_dir / "pca_fit_manifest.json")
    anom_man = _read_json(anom_dir / "anomaly_fit_manifest.json")

    fps = {
        "correlation": corr_man["dataset_fingerprint"]["sha256"],
        "pca": pca_man["dataset_fingerprint"]["sha256"],
        "anomaly": anom_man["dataset_fingerprint"]["sha256"],
    }
    if len(set(fps.values())) != 1:
        raise SystemExit(f"GATE FAILED: dataset fingerprints differ: {fps}")
    if anom_man["upstream"]["pca_run_id"] != pca_dir.name:
        raise SystemExit(
            "GATE FAILED: anomaly consumed pca run "
            f"{anom_man['upstream']['pca_run_id']!r}, expected {pca_dir.name!r}"
        )
    if not anom_man["upstream"]["pca_fingerprint_matches"]:
        raise SystemExit("GATE FAILED: anomaly/pca fingerprint mismatch recorded")
    if not (corr_man["features"] == pca_man["features"] == anom_man["features"]):
        raise SystemExit("GATE FAILED: feature scopes differ across components")
    windows = {
        k: (m["fit_window"]["train_start"], m["fit_window"]["train_end"])
        for k, m in (("corr", corr_man), ("pca", pca_man), ("anom", anom_man))
    }
    if len(set(windows.values())) != 1:
        raise SystemExit(f"GATE FAILED: train windows differ: {windows}")
    profiles = sorted(anom_man["profiles_supported"])
    if profiles != sorted(corr_man["profiles_fitted"]) or profiles != sorted(
        pca_man["profiles_fitted"]
    ):
        raise SystemExit("GATE FAILED: supported profiles differ across components")

    return {
        "behaviour_manifest": behaviour_man,
        "correlation_manifest": corr_man,
        "pca_manifest": pca_man,
        "anomaly_manifest": anom_man,
        "sha256": fps["anomaly"],
        "features": list(anom_man["features"]),
        "profiles": profiles,
        "train_start": pd.Timestamp(anom_man["fit_window"]["train_start"]),
        "train_end": pd.Timestamp(anom_man["fit_window"]["train_end"]),
        "n_train": int(anom_man["fit_window"]["n_train"]),
        "n_total": int(anom_man["fit_window"]["n_total"]),
        "index_end": pd.Timestamp(anom_man["dataset_fingerprint"]["index_end"]),
    }


def load_scores(anom_dir: Path, labels: pd.DataFrame) -> pd.DataFrame:
    """Anomaly scores + parsed trigger flags + is_train + day/hour buckets."""
    sc = pd.read_parquet(anom_dir / "scores" / "anomaly_scores.parquet")
    sc = sc.merge(labels[["timestamp", "is_train"]], on="timestamp", how="left")
    if sc["is_train"].isna().any():
        raise SystemExit("GATE FAILED: anomaly rows do not align with labels")
    sc["is_train"] = sc["is_train"].astype(bool)
    trig = sc["triggered_detectors"].fillna("")
    for d in DETECTORS:
        sc[f"trig_{d}"] = trig.str.contains(d, regex=False)
    sc["n_triggered"] = sc[[f"trig_{d}" for d in DETECTORS]].sum(axis=1)
    sc["all4_family"] = (
        sc["trig_statistical"]
        & sc["trig_mahalanobis"]
        & (sc["trig_pca_q"] | sc["trig_pca_t2"])
        & sc["trig_isolation_forest"]
    )
    sc["is_anomaly"] = sc["severity"] == "anomaly"
    sc["is_warning"] = sc["severity"] == "warning"
    sc["day"] = sc["timestamp"].dt.floor("D")
    sc["hour"] = sc["timestamp"].dt.floor("h")
    return sc


def load_labels() -> pd.DataFrame:
    return pd.read_parquet(BEHAVIOUR_DIR / "profiles" / "profile_labels.parquet")


def load_master(features: list[str]) -> pd.DataFrame:
    """Master dataset restricted to the 17-sensor scope, timestamp as column."""
    import pyarrow.parquet as pq

    names = pq.read_schema(MASTER_PATH).names
    ts_col = next((c for c in names if "timestamp" in c.lower()), None)
    if ts_col is not None:
        df = pd.read_parquet(MASTER_PATH, columns=[ts_col, *features])
        return df.rename(columns={ts_col: "timestamp"})
    df = pd.read_parquet(MASTER_PATH, columns=features).reset_index()
    df = df.rename(columns={df.columns[0]: "timestamp"})
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


# --------------------------------------------------------------------------
# Phase 1 — global timeline
# --------------------------------------------------------------------------


def aggregate_timeline(sc: pd.DataFrame, bucket: str) -> pd.DataFrame:
    g = sc.groupby(bucket)
    out = pd.DataFrame(
        {
            "n_rows": g.size(),
            "normal_rate": g["severity"].apply(lambda s: (s == "normal").mean()),
            "warning_rate": g["is_warning"].mean(),
            "anomaly_rate": g["is_anomaly"].mean(),
            "mean_combined": g["combined_score"].mean(),
            "p95_combined": g["combined_score"].apply(_p95),
            "all4_family_rate": g["all4_family"].mean(),
            "mean_n_triggered": g["n_triggered"].mean(),
        }
    )
    for d in DETECTORS:
        out[f"trig_rate_{d}"] = g[f"trig_{d}"].mean()
    return out.reset_index().rename(columns={bucket: "bucket"})


def top_affected_per_day(sc: pd.DataFrame, features: list[str]) -> pd.Series:
    dummies = sc["affected_variables"].fillna("").str.get_dummies(sep="|")
    dummies = dummies.reindex(columns=features, fill_value=0)
    daily = dummies.groupby(sc["day"]).sum()
    ranked = daily.apply(
        lambda r: "|".join(
            r.sort_values(ascending=False)
            .head(3)
            .index[r.sort_values(ascending=False).head(3) > 0]
        ),
        axis=1,
    )
    return ranked.rename("top_affected")


def first_sustained(
    daily: pd.DataFrame, thr: float, min_days: int = SUSTAINED_DAYS
) -> pd.Timestamp | None:
    """First day with anomaly_rate > thr starting >= min_days consecutive days."""
    above = (daily.set_index("bucket")["anomaly_rate"] > thr).astype(int)
    run = above.groupby((above != above.shift()).cumsum()).transform("size") * above
    hits = run[run >= min_days]
    return None if hits.empty else hits.index[0]


def characterize_timeline(
    daily: pd.DataFrame, train_end: pd.Timestamp
) -> dict[str, Any]:
    d = daily.set_index("bucket")
    val = d[d.index > train_end.floor("D")]
    steps = d["anomaly_rate"].diff()
    fs = first_sustained(daily, SUSTAINED_THR)
    post = d[d.index >= fs] if fs is not None else val
    plateau = float(post["anomaly_rate"].median()) if len(post) else float("nan")
    crossings = (
        int(
            (
                (post["anomaly_rate"] > SUSTAINED_THR)
                != (post["anomaly_rate"] > SUSTAINED_THR).shift()
            ).sum()
        )
        if len(post)
        else 0
    )
    rise_days = None
    if fs is not None and plateau == plateau:
        reached = post[post["anomaly_rate"] >= 0.8 * plateau]
        if len(reached):
            rise_days = int((reached.index[0] - fs).days)
    if rise_days is not None and rise_days <= 2 and crossings <= 4:
        shape = "abrupt"
    elif rise_days is not None and rise_days <= 14 and crossings <= 4:
        shape = "progressive"
    elif crossings > 4:
        shape = "episodic/mixed"
    else:
        shape = "mixed"
    last14 = post.tail(14)["anomaly_rate"]
    return {
        "sustained_rule": (
            f"first day with anomaly-severity rate > {SUSTAINED_THR:.0%} starting "
            f">= {SUSTAINED_DAYS} consecutive such days"
        ),
        "first_sustained_day": fs,
        "first_sustained_sensitivity": {
            f"thr_{int(t * 100)}pct": first_sustained(daily, t)
            for t in SENSITIVITY_THRS
        },
        "largest_step_day": steps.idxmax(),
        "largest_step_pp": float(steps.max()),
        "peak_day": d["anomaly_rate"].idxmax(),
        "peak_day_rate": float(d["anomaly_rate"].max()),
        "post_change_median_rate": plateau,
        "rise_days_to_80pct_plateau": rise_days,
        "threshold_crossings_post_change": crossings,
        "stabilized_last14d": bool(len(last14) >= 7 and float(last14.std()) < 0.15),
        "last14d_mean_rate": float(last14.mean()) if len(last14) else None,
        "shape": shape,
    }


# --------------------------------------------------------------------------
# Phase 2 — profile decomposition
# --------------------------------------------------------------------------


def profile_summary(sc: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    dummies = sc["affected_variables"].fillna("").str.get_dummies(sep="|")
    dummies = dummies.reindex(columns=features, fill_value=0)
    rows: list[dict[str, Any]] = []
    val_anoms = int(sc[~sc["is_train"]]["is_anomaly"].sum())
    for p, g in sc.groupby("profile"):
        v = g[~g["is_train"]]
        daily = aggregate_timeline(g, "day")
        fs = first_sustained(daily, SUSTAINED_THR)
        above = daily[daily["anomaly_rate"] > SUSTAINED_THR]
        ev = dummies.loc[v.index].sum().sort_values(ascending=False)
        ev = ev[ev > 0]
        row: dict[str, Any] = {
            "profile": p,
            "n_rows": len(g),
            "n_train": int(g["is_train"].sum()),
            "n_validation": len(v),
            "pct_of_validation_rows": len(v) / int((~sc["is_train"]).sum()),
            "n_anomaly_validation": int(v["is_anomaly"].sum()),
            "share_of_validation_anomalies": (
                int(v["is_anomaly"].sum()) / val_anoms if val_anoms else 0.0
            ),
            "anomaly_rate_validation": float(v["is_anomaly"].mean())
            if len(v)
            else None,
            "warning_rate_validation": float(v["is_warning"].mean())
            if len(v)
            else None,
            "anomaly_rate_train": float(g[g["is_train"]]["is_anomaly"].mean()),
            "mean_combined_validation": float(v["combined_score"].mean())
            if len(v)
            else None,
            "all4_family_rate_validation": float(v["all4_family"].mean())
            if len(v)
            else None,
            "first_sustained_day": fs,
            "n_days_above_threshold": len(above),
            "top_affected_validation": "|".join(ev.head(5).index),
        }
        for d in DETECTORS:
            row[f"trig_rate_validation_{d}"] = (
                float(v[f"trig_{d}"].mean()) if len(v) else None
            )
        rows.append(row)
    return pd.DataFrame(rows).sort_values(
        "share_of_validation_anomalies", ascending=False
    )


# --------------------------------------------------------------------------
# Phase 3 — sensor forensics
# --------------------------------------------------------------------------


def _window_stats(s: pd.Series) -> dict[str, Any]:
    q = s.quantile([0.05, 0.25, 0.50, 0.75, 0.95])
    return {
        "count": int(s.count()),
        "missing_rate": float(s.isna().mean()),
        "n_unique": int(s.nunique()),
        "mean": float(s.mean()),
        "median": float(s.median()),
        "std": float(s.std()),
        "p05": float(q[0.05]),
        "p25": float(q[0.25]),
        "p50": float(q[0.50]),
        "p75": float(q[0.75]),
        "p95": float(q[0.95]),
        "iqr": float(q[0.75] - q[0.25]),
        "near_constant": bool(s.std() < 1e-9 or s.nunique() <= 1),
    }


def sensor_shift_summary(
    m: pd.DataFrame, sc: pd.DataFrame, features: list[str]
) -> pd.DataFrame:
    masks = {
        "train": m["is_train"],
        "validation_sep": ~m["is_train"] & (m["timestamp"] < OCT_START),
        "validation_oct": ~m["timestamp"].lt(OCT_START) & ~m["is_train"],
    }
    dummies = sc["affected_variables"].fillna("").str.get_dummies(sep="|")
    dummies = dummies.reindex(columns=features, fill_value=0)
    val_flag = ~sc["is_train"] & (sc["severity"] != "normal")
    ev_by_profile = dummies[val_flag].groupby(sc.loc[val_flag, "profile"]).sum()
    rows: list[dict[str, Any]] = []
    for f in features:
        train_stats = _window_stats(m.loc[masks["train"], f])
        for window, mask in masks.items():
            st = _window_stats(m.loc[mask, f])
            st.update({"sensor": f, "window": window})
            if window != "train":
                med_shift = st["median"] - train_stats["median"]
                st["abs_median_shift"] = abs(med_shift)
                st["rel_median_shift"] = (
                    med_shift / abs(train_stats["median"])
                    if abs(train_stats["median"]) > 1e-9
                    else None
                )
                st["std_change_ratio"] = (
                    st["std"] / train_stats["std"]
                    if train_stats["std"] > 1e-9
                    else None
                )
                st["iqr_change_ratio"] = (
                    st["iqr"] / train_stats["iqr"]
                    if train_stats["iqr"] > 1e-9
                    else None
                )
            st["evidence_count_validation"] = int(dummies.loc[val_flag, f].sum())
            st["evidence_by_profile_json"] = json.dumps(
                ev_by_profile[f].astype(int).to_dict() if f in ev_by_profile else {}
            )
            st["is_steam_sensor"] = f in STEAM_SENSORS
            rows.append(st)
    return pd.DataFrame(rows)


def _max_consecutive_identical(s: pd.Series) -> int:
    v = s.dropna()
    if v.empty:
        return 0
    runs = (v != v.shift()).cumsum()
    return int(runs.groupby(runs).size().max())


def sensor_quality_diagnostics(m: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    masks = {
        "train": m["is_train"],
        "validation_sep": ~m["is_train"] & (m["timestamp"] < OCT_START),
        "validation_oct": ~m["is_train"] & (m["timestamp"] >= OCT_START),
    }
    rows: list[dict[str, Any]] = []
    for f in features:
        tr = m.loc[masks["train"], f]
        robust_std = float((tr.quantile(0.75) - tr.quantile(0.25)) / 1.349) or float(
            tr.std() or 1.0
        )
        tmin, tmax = float(tr.min()), float(tr.max())
        for window, mask in masks.items():
            sub = m.loc[mask, [f, "timestamp"]]
            s = sub[f]
            dm = s.groupby(sub["timestamp"].dt.floor("D")).median()
            daily_missing = s.isna().groupby(sub["timestamp"].dt.floor("D")).mean()
            step = dm.diff().abs()
            var_ratio = float(s.var() / tr.var()) if tr.var() > 1e-12 else None
            rows.append(
                {
                    "sensor": f,
                    "window": window,
                    "max_consecutive_identical": _max_consecutive_identical(s),
                    "frozen_suspect": _max_consecutive_identical(s)
                    > max(60, int(0.05 * len(s))),
                    "max_daily_median_step_robust_z": (
                        float(step.max() / robust_std) if len(step.dropna()) else None
                    ),
                    "offset_suspect": bool(
                        len(step.dropna()) and step.max() / robust_std > 5.0
                    ),
                    "n_below_train_min": int((s < tmin).sum()),
                    "n_above_train_max": int((s > tmax).sum()),
                    "max_daily_missing_rate": float(daily_missing.max())
                    if len(daily_missing)
                    else None,
                    "missingness_spike": bool(
                        len(daily_missing) and daily_missing.max() > 0.5
                    ),
                    "variance_ratio_vs_train": var_ratio,
                    "variance_collapse": bool(
                        var_ratio is not None and var_ratio < 0.1
                    ),
                    "variance_explosion": bool(
                        var_ratio is not None and var_ratio > 10.0
                    ),
                    "share_at_window_min": float((s == s.min()).mean())
                    if s.count()
                    else None,
                    "share_at_window_max": float((s == s.max()).mean())
                    if s.count()
                    else None,
                    "saturation_suspect": bool(
                        s.count()
                        and max((s == s.min()).mean(), (s == s.max()).mean()) > 0.2
                    ),
                    "is_steam_sensor": f in STEAM_SENSORS,
                }
            )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Phase 4 — correlation shift
# --------------------------------------------------------------------------


def correlation_shift_ranked(
    corr_dir: Path, m: pd.DataFrame, labels: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, Any]]:
    shift = pd.read_parquet(corr_dir / "correlation_shift.parquet")
    train_corrs = pd.read_parquet(corr_dir / "correlations.parquet")
    mm = m.merge(labels[["timestamp", "profile"]], on="timestamp", how="left")
    sp_rows: list[dict[str, Any]] = []
    for p, pairs in shift.groupby("profile"):
        sub = mm[mm["profile"] == p]
        tr, va = sub[sub["is_train"]], sub[~sub["is_train"]]
        for _, r in pairs.iterrows():
            a, b = r["feature_a"], r["feature_b"]
            row = {"profile": p, "feature_a": a, "feature_b": b}
            for name, w in (("spearman_train", tr), ("spearman_validation", va)):
                pair = w[[a, b]].dropna()
                row[name] = (
                    float(pair[a].corr(pair[b], method="spearman"))
                    if len(pair) >= 200
                    else None
                )
            sp_rows.append(row)
    sp = pd.DataFrame(sp_rows)
    out = shift.merge(sp, on=["profile", "feature_a", "feature_b"], how="left")
    out = out.rename(columns={"abs_delta": "pearson_abs_delta"})
    out["spearman_abs_delta"] = (
        out["spearman_validation"] - out["spearman_train"]
    ).abs()
    out["sign_flip_pearson"] = (
        (out["pearson_train"] * out["pearson_validation"] < 0)
        & (out["pearson_train"].abs() > 0.3)
        & (out["pearson_validation"].abs() > 0.3)
    )
    out["weakened"] = (out["pearson_train"].abs() >= 0.8) & (
        out["pearson_validation"].abs() < 0.5
    )
    out["emerging"] = (out["pearson_train"].abs() < 0.5) & (
        out["pearson_validation"].abs() >= 0.8
    )
    out["involves_steam"] = out["feature_a"].isin(STEAM_SENSORS) | out[
        "feature_b"
    ].isin(STEAM_SENSORS)
    out = out.sort_values("pearson_abs_delta", ascending=False).reset_index(drop=True)

    # Cross-check recomputed train Spearman against the persisted reference.
    chk = out.merge(
        train_corrs[["profile", "feature_a", "feature_b", "spearman"]],
        on=["profile", "feature_a", "feature_b"],
        how="inner",
    )
    diffs = (chk["spearman_train"] - chk["spearman"]).abs().dropna()
    broad = (
        out.assign(shifted=out["pearson_abs_delta"] > 0.2)
        .groupby("profile")["shifted"]
        .mean()
        .to_dict()
    )
    diag = {
        "spearman_train_crosscheck_max_abs_diff": float(diffs.max())
        if len(diffs)
        else None,
        "n_sign_flips": int(out["sign_flip_pearson"].sum()),
        "n_weakened": int(out["weakened"].sum()),
        "n_emerging": int(out["emerging"].sum()),
        "share_pairs_shifted_gt_0.2_by_profile": broad,
    }
    return out, diag


# --------------------------------------------------------------------------
# Phase 5 — PCA forensics
# --------------------------------------------------------------------------


def pca_diagnostics(
    pca_dir: Path, facts: dict[str, Any]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    pca_man = facts["pca_manifest"]
    thresholds = facts["anomaly_manifest"]["pca_thresholds"]
    rows: list[dict[str, Any]] = []
    daily_frames: list[pd.DataFrame] = []
    for p in facts["profiles"]:
        s = pd.read_parquet(pca_dir / "scores" / p / "scores.parquet")
        s["is_train"] = s["is_train"].astype(bool)
        contrib = pd.read_parquet(pca_dir / "scores" / p / "contributions.parquet")
        contrib = contrib.merge(s[["timestamp", "is_train"]], on="timestamp")
        tr, va = s[s["is_train"]], s[~s["is_train"]]
        day = s["timestamp"].dt.floor("D")
        daily = s.groupby(day).agg(
            q_median=("q_spe", "median"),
            t2_median=("t2", "median"),
            recon_median=("recon_error", "median"),
        )
        daily["profile"] = p
        daily_frames.append(daily.reset_index().rename(columns={"timestamp": "day"}))
        cm = (
            contrib[~contrib["is_train"]].drop(columns=["timestamp", "is_train"]).mean()
        )
        cs = cm / cm.sum() if cm.sum() > 0 else cm
        top3 = cs.sort_values(ascending=False).head(3)
        vh1 = va[va["timestamp"] < va["timestamp"].min() + pd.Timedelta(days=7)]
        row: dict[str, Any] = {
            "profile": p,
            "n_components": pca_man["profiles"][p]["n_components"],
            "cumulative_evr": pca_man["profiles"][p]["cumulative_evr"],
            "n_train": len(tr),
            "n_validation": len(va),
            "q_median_train": float(tr["q_spe"].median()),
            "q_median_validation": float(va["q_spe"].median()) if len(va) else None,
            "q_p95_train": _p95(tr["q_spe"]),
            "q_p95_validation": _p95(va["q_spe"]) if len(va) else None,
            "t2_median_train": float(tr["t2"].median()),
            "t2_median_validation": float(va["t2"].median()) if len(va) else None,
            "recon_median_train": float(tr["recon_error"].median()),
            "recon_median_validation": (
                float(va["recon_error"].median()) if len(va) else None
            ),
            "q_ks_statistic": float(stats.ks_2samp(tr["q_spe"], va["q_spe"]).statistic)
            if len(va)
            else None,
            "t2_ks_statistic": float(stats.ks_2samp(tr["t2"], va["t2"]).statistic)
            if len(va)
            else None,
            "share_validation_above_q_threshold": (
                float((va["q_spe"] > thresholds[p]["q"]).mean()) if len(va) else None
            ),
            "share_validation_above_t2_threshold": (
                float((va["t2"] > thresholds[p]["t2"]).mean()) if len(va) else None
            ),
            "share_first7d_validation_above_q_threshold": (
                float((vh1["q_spe"] > thresholds[p]["q"]).mean()) if len(vh1) else None
            ),
            "top3_validation_contributors": "|".join(top3.index),
            "top3_contribution_share": float(top3.sum()),
            "deviation_concentrated_3_sensors": bool(top3.sum() > 0.6),
        }
        rows.append(row)
    return pd.DataFrame(rows), pd.concat(daily_frames, ignore_index=True)


# --------------------------------------------------------------------------
# Phase 6 — detector agreement
# --------------------------------------------------------------------------


def detector_agreement(
    sc: pd.DataFrame, anom_dir: Path
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    def combos(g: pd.DataFrame, scope: dict[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        n = len(g)
        sets: list[tuple[str, pd.Series]] = [(d, g[f"trig_{d}"]) for d in DETECTORS]
        for i in range(len(DETECTORS)):
            for j in range(i + 1, len(DETECTORS)):
                a, b = DETECTORS[i], DETECTORS[j]
                sets.append((f"{a}|{b}", g[f"trig_{a}"] & g[f"trig_{b}"]))
        sets.append(("ALL4_FAMILY", g["all4_family"]))
        sets.append(("ALL5", g["n_triggered"] == 5))
        sets.append(("TRIPLE_OR_MORE", g["n_triggered"] >= 3))
        for name, mask in sets:
            out.append(
                {
                    **scope,
                    "detector_set": name,
                    "n_rows": n,
                    "n_triggered": int(mask.sum()),
                    "rate": float(mask.mean()) if n else None,
                }
            )
        return out

    rows: list[dict[str, Any]] = []
    by_profile: list[dict[str, Any]] = []
    for window, mask in (
        ("train", sc["is_train"]),
        ("validation", ~sc["is_train"]),
        ("all", pd.Series(True, index=sc.index)),
    ):
        rows += combos(sc[mask], {"window": window})
        for p, g in sc[mask].groupby("profile"):
            by_profile += combos(g, {"window": window, "profile": p})

    # Cross-check pairwise counts (window=all) against the persisted summary.
    persisted = pd.read_parquet(anom_dir / "summaries" / "detector_agreement.parquet")
    bp = pd.DataFrame(by_profile)
    mismatches = 0
    for _, r in persisted.iterrows():
        key = f"{r['detector_a']}|{r['detector_b']}"
        alt = f"{r['detector_b']}|{r['detector_a']}"
        ours = bp[
            (bp["window"] == "all")
            & (bp["profile"] == r["profile"])
            & (bp["detector_set"].isin([key, alt]))
        ]["n_triggered"]
        if len(ours) != 1 or int(ours.iloc[0]) != int(r["n_both_triggered"]):
            mismatches += 1
    return (
        pd.DataFrame(rows),
        bp,
        {
            "persisted_pairwise_crosscheck_mismatches": mismatches,
            "persisted_pairwise_rows": len(persisted),
        },
    )


# --------------------------------------------------------------------------
# Phase 7 — change-point candidates
# --------------------------------------------------------------------------


def change_point_candidates(
    daily: pd.DataFrame,
    sc: pd.DataFrame,
    m: pd.DataFrame,
    pca_daily: pd.DataFrame,
    features: list[str],
    train_end: pd.Timestamp,
) -> pd.DataFrame:
    d = daily.set_index("bucket")
    signals: list[dict[str, Any]] = []

    fs = first_sustained(daily, SUSTAINED_THR)
    if fs is not None:
        signals.append(
            {
                "day": fs,
                "signal": "anomaly_rate_sustained",
                "detail": f">{SUSTAINED_THR:.0%} for >={SUSTAINED_DAYS}d",
            }
        )
    steps = d["anomaly_rate"].diff()
    for day, v in steps[steps > 0.25].items():
        signals.append(
            {
                "day": day,
                "signal": "anomaly_rate_step",
                "detail": f"+{v:.0%} day-over-day",
            }
        )
    roll = d["anomaly_rate"].rolling(7).mean()
    jump = roll - roll.shift(7)
    for day, v in jump[jump > 0.20].items():
        signals.append(
            {
                "day": day,
                "signal": "rolling7d_rate_jump",
                "detail": f"+{v:.0%} vs prior week",
            }
        )

    for f in features:
        sub = m[["timestamp", f]]
        tr = m.loc[m["is_train"], f]
        robust = float((tr.quantile(0.75) - tr.quantile(0.25)) / 1.349) or float(
            tr.std() or 1.0
        )
        dm = sub.set_index("timestamp")[f].resample("D").median()
        dev = ((dm - tr.median()).abs() / robust) > 3.0
        run = dev.groupby((dev != dev.shift()).cumsum()).transform("size") * dev
        hits = run[(run >= SUSTAINED_DAYS) & (run.index > train_end.floor("D"))]
        if not hits.empty:
            signals.append(
                {"day": hits.index[0], "signal": "sensor_median_shift", "detail": f}
            )

    agr = d["all4_family_rate"].diff()
    for day, v in agr[agr > 0.2].items():
        signals.append(
            {"day": day, "signal": "detector_agreement_jump", "detail": f"+{v:.0%}"}
        )

    gq = pca_daily.groupby("day")["q_median"].median()
    qd = gq.diff().abs()
    qstd = float(qd[qd.index <= train_end.floor("D")].std() or 1.0)
    for day, v in qd[(qd > 5 * qstd) & (qd.index > train_end.floor("D"))].items():
        signals.append(
            {
                "day": day,
                "signal": "pca_q_jump",
                "detail": f"daily-median Q step {v:.3g}",
            }
        )

    cs = sc.set_index("timestamp")["combined_score"].resample("D").mean().dropna()
    for day in [
        x["day"]
        for x in signals
        if x["signal"] in ("anomaly_rate_sustained", "anomaly_rate_step")
    ]:
        before = cs[(cs.index >= day - pd.Timedelta(days=7)) & (cs.index < day)]
        after = cs[(cs.index >= day) & (cs.index < day + pd.Timedelta(days=7))]
        if len(before) >= 3 and len(after) >= 3:
            ks = float(stats.ks_2samp(before, after).statistic)
            if ks > 0.5:
                signals.append(
                    {
                        "day": day,
                        "signal": "ks_window_shift",
                        "detail": f"KS={ks:.2f} (7d daily means)",
                    }
                )

    sig = pd.DataFrame(signals)
    if sig.empty:
        return pd.DataFrame(
            columns=[
                "candidate_day",
                "n_signal_types",
                "signals",
                "sensors",
                "persistence_days",
                "anomaly_rate_before",
                "anomaly_rate_after",
                "affected_profiles",
                "confidence",
            ]
        )
    sig = sig.sort_values("day").reset_index(drop=True)
    sig["cluster"] = (sig["day"].diff() > pd.Timedelta(days=2)).cumsum()

    cands: list[dict[str, Any]] = []
    for _, g in sig.groupby("cluster"):
        day = g["day"].min()
        kinds = sorted(g["signal"].unique())
        sensors = sorted(g.loc[g["signal"] == "sensor_median_shift", "detail"].unique())
        before = d.loc[d.index < day, "anomaly_rate"].tail(7).mean()
        after = d.loc[d.index >= day, "anomaly_rate"].head(7).mean()
        post = d.loc[d.index >= day, "anomaly_rate"]
        persist = int((post > SUSTAINED_THR).cumprod().sum())
        prof_day = sc[(sc["day"] >= day) & (sc["day"] < day + pd.Timedelta(days=7))]
        prof_rates = prof_day.groupby("profile")["is_anomaly"].mean()
        affected = "|".join(sorted(prof_rates[prof_rates > SUSTAINED_THR].index))
        n_types = len(kinds)
        confidence = "high" if n_types >= 4 else ("medium" if n_types >= 2 else "low")
        cands.append(
            {
                "candidate_day": day,
                "n_signal_types": n_types,
                "signals": "|".join(kinds),
                "sensors": "|".join(sensors),
                "persistence_days": persist,
                "anomaly_rate_before": float(before) if before == before else None,
                "anomaly_rate_after": float(after) if after == after else None,
                "affected_profiles": affected,
                "confidence": confidence,
            }
        )
    return (
        pd.DataFrame(cands)
        .sort_values(["n_signal_types", "persistence_days"], ascending=False)
        .reset_index(drop=True)
    )


# --------------------------------------------------------------------------
# Phase 8 — top-event review pack
# --------------------------------------------------------------------------


def _dedup_pick(g: pd.DataFrame, k: int, hours: float = 6.0) -> pd.DataFrame:
    picked: list[int] = []
    for idx, row in g.sort_values("combined_score", ascending=False).iterrows():
        if all(
            abs((row["timestamp"] - g.loc[j, "timestamp"]).total_seconds())
            > hours * 3600
            for j in picked
        ):
            picked.append(idx)
        if len(picked) >= k:
            break
    return g.loc[picked]


def top_events_review(
    sc: pd.DataFrame,
    fs_day: pd.Timestamp | None,
    quality: pd.DataFrame,
) -> pd.DataFrame:
    val = sc[~sc["is_train"] & (sc["severity"] == "anomaly")]
    steam_hits = (
        val["affected_variables"]
        .fillna("")
        .apply(lambda v: sum(s in v for s in STEAM_SENSORS))
    )
    qsus = quality[
        (quality["window"] != "train")
        & (
            quality["frozen_suspect"]
            | quality["offset_suspect"]
            | quality["variance_collapse"]
            | quality["variance_explosion"]
            | quality["saturation_suspect"]
        )
    ]
    qs_sensors = sorted(qsus["sensor"].unique())
    last7 = val[val["timestamp"] >= val["timestamp"].max() - pd.Timedelta(days=7)]
    weekly = val.assign(week=val["timestamp"].dt.to_period("W").dt.start_time)
    weekly_top = (
        weekly.sort_values("combined_score", ascending=False).groupby("week").head(1)
    )

    cats: list[tuple[str, pd.DataFrame, int, str]] = [
        (
            "earliest_sustained",
            val[val["day"] >= fs_day].sort_values("timestamp").head(50)
            if fs_day is not None
            else val.sort_values("timestamp").head(50),
            3,
            "first anomaly-severity rows at/after the first sustained deviation day",
        ),
        ("highest_combined", val, 3, "highest combined scores in validation"),
        (
            "strongest_agreement",
            val[val["n_triggered"] == val["n_triggered"].max()],
            3,
            "maximum simultaneous detector triggers",
        ),
        (
            "steam_evidence",
            val[steam_hits >= 2],
            3,
            ">=2 steam-system sensors in affected variables",
        ),
        (
            "stopped_profile",
            val[val["profile"] == "stopped"],
            3,
            "strongest stopped-profile events",
        ),
        (
            "startup_profile",
            val[val["profile"] == "startup"],
            3,
            "strongest startup-profile events",
        ),
        (
            "production_profiles",
            val[
                val["profile"].isin(
                    ["low_production", "mid_production", "high_production"]
                )
            ],
            3,
            "strongest production-profile events",
        ),
        (
            "sensor_quality_suspect",
            val[
                val["affected_variables"]
                .fillna("")
                .apply(lambda v: any(s in v for s in qs_sensors))
            ]
            if qs_sensors
            else val.head(0),
            2,
            f"evidence includes quality-flagged sensors ({'|'.join(qs_sensors[:4])})",
        ),
        (
            "stable_new_regime",
            last7[
                (last7["combined_score"] >= last7["combined_score"].quantile(0.45))
                & (last7["combined_score"] <= last7["combined_score"].quantile(0.55))
            ],
            2,
            "median-score events from the final week — representative of the plateau",
        ),
        ("progressive_degradation", weekly_top, 4, "weekly top events — trend readout"),
    ]
    packs: list[pd.DataFrame] = []
    for name, pool, k, reason in cats:
        if pool.empty:
            continue
        if name == "earliest_sustained":
            pick = pool.head(1)
            rest = pool.iloc[1:]
            pick = pd.concat([pick, _dedup_pick(rest, k - 1)]) if len(rest) else pick
        elif name == "progressive_degradation":
            pick = pool.sort_values("timestamp").head(k)
        else:
            pick = _dedup_pick(pool, k)
        pick = pick.copy()
        pick["category"] = name
        pick["selection_reason"] = reason
        packs.append(pick)
    pack = pd.concat(packs, ignore_index=True)
    rates = sc.set_index("timestamp")["is_anomaly"]
    pack["context_anomaly_rate_pm30min"] = pack["timestamp"].apply(
        lambda t: float(
            rates[
                (rates.index >= t - pd.Timedelta(minutes=30))
                & (rates.index <= t + pd.Timedelta(minutes=30))
            ].mean()
        )
    )
    cols = [
        "category",
        "selection_reason",
        "timestamp",
        "profile",
        "severity",
        "combined_score",
        "triggered_detectors",
        *[f"{d}_score" for d in DETECTORS],
        "affected_variables",
        "evidence",
        "context_anomaly_rate_pm30min",
    ]
    return pack[cols]


# --------------------------------------------------------------------------
# Phase 9 — figures
# --------------------------------------------------------------------------


def _boundary(ax: plt.Axes, train_end: pd.Timestamp) -> None:
    ax.axvline(
        train_end,
        color="black",
        linestyle="--",
        linewidth=1,
        label="train/validation boundary",
    )


def make_figures(
    out: Path,
    daily: pd.DataFrame,
    daily_by_profile: pd.DataFrame,
    m: pd.DataFrame,
    pca_daily: pd.DataFrame,
    cands: pd.DataFrame,
    sensor_shift: pd.DataFrame,
    train_end: pd.Timestamp,
) -> list[str]:
    made: list[str] = []
    d = daily.set_index("bucket")

    def save(fig: plt.Figure, name: str) -> None:
        fig.autofmt_xdate()
        fig.tight_layout()
        fig.savefig(out / name, dpi=120)
        plt.close(fig)
        made.append(name)

    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(d.index, d["anomaly_rate"], label="daily anomaly rate", color="firebrick")
    ax.plot(
        d.index,
        d["warning_rate"],
        label="daily warning rate",
        color="orange",
        alpha=0.7,
    )
    ax.axhline(
        SUSTAINED_THR,
        color="gray",
        linestyle=":",
        label=f"sustained threshold ({SUSTAINED_THR:.0%})",
    )
    _boundary(ax, train_end)
    ax.set(
        title="Daily anomaly-severity rate (anomaly run 20260611T173316Z)",
        xlabel="day",
        ylabel="rate",
    )
    ax.legend(loc="upper left", fontsize=8)
    save(fig, "daily_anomaly_rate.png")

    fig, ax = plt.subplots(figsize=(11, 5))
    for p, g in daily_by_profile.groupby("profile"):
        ax.plot(g["bucket"], g["anomaly_rate"], label=p, alpha=0.8)
    _boundary(ax, train_end)
    ax.set(title="Daily anomaly rate by profile", xlabel="day", ylabel="anomaly rate")
    ax.legend(loc="upper left", fontsize=7, ncol=2)
    save(fig, "daily_anomaly_rate_by_profile.png")

    fig, ax = plt.subplots(figsize=(11, 4))
    for det in DETECTORS:
        ax.plot(d.index, d[f"trig_rate_{det}"], label=det, alpha=0.8)
    _boundary(ax, train_end)
    ax.set(title="Daily detector trigger rates", xlabel="day", ylabel="trigger rate")
    ax.legend(loc="upper left", fontsize=8)
    save(fig, "detector_trigger_rates_over_time.png")

    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(
        d.index,
        d["all4_family_rate"],
        color="purple",
        label="all-4-family co-trigger rate",
    )
    ax.plot(
        d.index,
        d["mean_n_triggered"] / 5,
        color="teal",
        alpha=0.7,
        label="mean #triggered / 5",
    )
    _boundary(ax, train_end)
    ax.set(title="Detector agreement over time", xlabel="day", ylabel="rate")
    ax.legend(loc="upper left", fontsize=8)
    save(fig, "detector_agreement_over_time.png")

    shifts = (
        sensor_shift[sensor_shift["window"] == "validation_sep"]
        .set_index("sensor")["abs_median_shift"]
        .sort_values(ascending=False)
        .head(10)
    )
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.barh(shifts.index[::-1], shifts.values[::-1], color="steelblue")
    ax.set(
        title="Top-10 absolute median shifts: train vs September validation",
        xlabel="absolute median shift (engineering units)",
    )
    save(fig, "top_sensor_shifts.png")

    fig, axes = plt.subplots(len(STEAM_SENSORS), 1, figsize=(11, 7), sharex=True)
    for ax, sensor in zip(axes, STEAM_SENSORS, strict=True):
        sub = m.set_index("timestamp")[sensor].resample("D")
        med, q1, q3 = sub.median(), sub.quantile(0.25), sub.quantile(0.75)
        ax.plot(med.index, med, color="darkgreen", label="daily median")
        ax.fill_between(
            med.index, q1, q3, alpha=0.25, color="darkgreen", label="daily IQR"
        )
        _boundary(ax, train_end)
        ax.set_ylabel(sensor, fontsize=7)
        ax.legend(loc="upper left", fontsize=6)
    axes[0].set_title("Steam-system sensors: daily median and IQR")
    axes[-1].set_xlabel("day")
    save(fig, "steam_system_timeline.png")

    fig, ax = plt.subplots(figsize=(11, 4.5))
    for p, g in pca_daily.groupby("profile"):
        ax.plot(g["day"], g["q_median"], label=p, alpha=0.8)
    _boundary(ax, train_end)
    ax.set_yscale("log")
    ax.set(
        title="PCA Q-residual (daily median, per profile, log scale)",
        xlabel="day",
        ylabel="Q / SPE",
    )
    ax.legend(loc="upper left", fontsize=7, ncol=2)
    save(fig, "pca_q_residual_over_time.png")

    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(d.index, d["anomaly_rate"], color="firebrick", label="daily anomaly rate")
    colors = {"high": "darkred", "medium": "darkorange", "low": "gray"}
    for _, r in cands.iterrows():
        ax.axvline(
            r["candidate_day"], color=colors[r["confidence"]], alpha=0.8, linestyle="-."
        )
        ax.annotate(
            r["confidence"], (r["candidate_day"], 0.95), fontsize=6, rotation=90
        )
    _boundary(ax, train_end)
    ax.set(
        title="Candidate change points (review points, not confirmed root causes)",
        xlabel="day",
        ylabel="anomaly rate",
    )
    ax.legend(loc="upper left", fontsize=8)
    save(fig, "candidate_change_points.png")
    return made


# --------------------------------------------------------------------------
# limitations + manifest
# --------------------------------------------------------------------------


def write_limitations(out: Path, findings: dict[str, Any]) -> None:
    sens = findings["timeline"]["first_sustained_sensitivity"]
    text = f"""# Limitations — September–October forensic analysis

- **No ground-truth labels.** All severities derive from *training-window*
  percentile thresholds; "anomaly" means "different from June–August normal",
  not a confirmed machine fault.
- **Sustained-deviation rule is a convention**: {findings["timeline"]["sustained_rule"]}.
  Sensitivity: at 25% the first sustained day is {sens.get("thr_25pct")}, at 50%
  it is {sens.get("thr_50pct")}. Conclusions about *timing shape* are robust to
  the threshold; the exact first day is not.
- **PCA T²/Q train thresholds are marginally tight** (train scored in-sample,
  documented upstream); validation exceedance shares are therefore slightly
  conservative-biased upward.
- **Validation Spearman correlations were recomputed** from the master dataset
  (pairwise-complete, min 200 obs) because only Pearson shift is persisted;
  recomputed train values were cross-checked against the persisted reference
  (max abs diff: {findings["correlation"]["spearman_train_crosscheck_max_abs_diff"]}).
- **Mahalanobis contributions are signed and non-partitioning** — they rank
  evidence, they do not apportion blame (upstream documentation §7).
- **Correlation does not imply causation**; sensor co-movement changes are
  treated as descriptive evidence only.
- **No plant records were available** (recipes, batches, maintenance,
  recalibrations). Several hypotheses are observationally equivalent without
  them — see executive summary §F.
- Candidate change points are **review points**, not confirmed events.
"""
    (out / "limitations.md").write_text(text, encoding="utf-8")


def finalize_manifest(run_id: str) -> None:
    """Write forensic_manifest.json last — marks the forensic run complete."""
    out = run_dir(FORENSICS_ROOT, run_id)
    if not out.is_dir():
        raise SystemExit(f"No forensic run directory: {out}")
    inventory = sorted(p.name for p in out.iterdir() if p.is_file())
    facts = load_and_gate(
        run_dir(INTELLIGENCE_DIR / "correlation", CORR_RUN_ID),
        run_dir(INTELLIGENCE_DIR / "pca", PCA_RUN_ID),
        run_dir(INTELLIGENCE_DIR / "anomaly", ANOM_RUN_ID),
    )
    manifest = {
        "component": "forensics",
        "forensic_run_id": run_id,
        "created_utc": datetime.now(UTC).isoformat(),
        "read_only": True,
        "statements": [
            "No fit procedure was invoked.",
            "No upstream artifacts were modified or overwritten.",
            "No thresholds, profiles, or reference windows were changed.",
        ],
        "master_dataset_path": str(MASTER_PATH),
        "master_dataset_sha256_structural": facts["sha256"],
        "behaviour_artifacts": str(BEHAVIOUR_DIR),
        "correlation_run": {
            "run_id": CORR_RUN_ID,
            "path": str(run_dir(INTELLIGENCE_DIR / "correlation", CORR_RUN_ID)),
        },
        "pca_run": {
            "run_id": PCA_RUN_ID,
            "path": str(run_dir(INTELLIGENCE_DIR / "pca", PCA_RUN_ID)),
        },
        "anomaly_run": {
            "run_id": ANOM_RUN_ID,
            "path": str(run_dir(INTELLIGENCE_DIR / "anomaly", ANOM_RUN_ID)),
        },
        "train_window": {
            "start": str(facts["train_start"]),
            "end": str(facts["train_end"]),
            "n_rows": facts["n_train"],
        },
        "validation_window": {
            "start": str(facts["train_end"]),
            "end": str(facts["index_end"]),
            "n_rows": facts["n_total"] - facts["n_train"],
        },
        "feature_scope": facts["features"],
        "supported_profiles": facts["profiles"],
        "scripts_executed": ["scripts/analysis/forensic_sep_oct.py"],
        "generated_files": inventory,
    }
    _write_json(out / "forensic_manifest.json", manifest)
    log.info("Forensic manifest written: %s", out / "forensic_manifest.json")


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def run_analysis() -> int:
    corr_dir = run_dir(INTELLIGENCE_DIR / "correlation", CORR_RUN_ID)
    pca_dir = run_dir(INTELLIGENCE_DIR / "pca", PCA_RUN_ID)
    anom_dir = run_dir(INTELLIGENCE_DIR / "anomaly", ANOM_RUN_ID)
    facts = load_and_gate(corr_dir, pca_dir, anom_dir)
    log.info(
        "Gate passed: sha256 %s…, %d features, %d profiles",
        facts["sha256"][:12],
        len(facts["features"]),
        len(facts["profiles"]),
    )

    run_id = new_run_id(FORENSICS_ROOT)
    out = run_dir(FORENSICS_ROOT, run_id)
    out.mkdir(parents=True, exist_ok=False)
    log.info("Forensic run: %s", out)

    labels = load_labels()
    sc = load_scores(anom_dir, labels)
    m = load_master(facts["features"]).merge(
        labels[["timestamp", "is_train"]], on="timestamp", how="inner"
    )
    if len(m) != facts["n_total"]:
        raise SystemExit("GATE FAILED: master/labels timestamp alignment")
    m["is_train"] = m["is_train"].astype(bool)
    inventory = {
        "anomaly_scores": {
            "rows": len(sc),
            "columns": [
                c
                for c in sc.columns
                if not c.startswith(("trig_", "is_", "day", "hour", "n_trig", "all4"))
            ],
        },
        "profile_labels": {"rows": len(labels), "columns": list(labels.columns)},
        "master_scope": {"rows": len(m), "columns": facts["features"]},
        "upstream_runs": {
            "correlation": CORR_RUN_ID,
            "pca": PCA_RUN_ID,
            "anomaly": ANOM_RUN_ID,
        },
    }

    findings: dict[str, Any] = {"run_id": run_id}

    log.info("Phase 1: global timeline")
    hourly = aggregate_timeline(sc, "hour")
    daily = aggregate_timeline(sc, "day")
    daily = daily.merge(
        top_affected_per_day(sc, facts["features"])
        .reset_index()
        .rename(columns={"day": "bucket"}),
        on="bucket",
        how="left",
    )
    hourly.to_parquet(out / "timeline_hourly.parquet", index=False)
    daily.to_parquet(out / "timeline_daily.parquet", index=False)
    findings["timeline"] = characterize_timeline(daily, facts["train_end"])
    val_rows = sc[~sc["is_train"]]
    findings["headline"] = {
        "validation_rows": len(val_rows),
        "validation_anomaly_rate": float(val_rows["is_anomaly"].mean()),
        "validation_warning_rate": float(val_rows["is_warning"].mean()),
        "train_anomaly_rate": float(sc[sc["is_train"]]["is_anomaly"].mean()),
    }

    log.info("Phase 2: profile decomposition")
    dbp = (
        sc.groupby(["day", "profile"])
        .agg(
            n_rows=("severity", "size"),
            anomaly_rate=("is_anomaly", "mean"),
            warning_rate=("is_warning", "mean"),
            mean_combined=("combined_score", "mean"),
            all4_family_rate=("all4_family", "mean"),
            mean_n_triggered=("n_triggered", "mean"),
        )
        .reset_index()
        .rename(columns={"day": "bucket"})
    )
    dbp.to_parquet(out / "timeline_daily_by_profile.parquet", index=False)
    prof = profile_summary(sc, facts["features"])
    prof.to_parquet(out / "profile_drift_summary.parquet", index=False)
    findings["profiles"] = prof[
        [
            "profile",
            "share_of_validation_anomalies",
            "anomaly_rate_validation",
            "first_sustained_day",
            "top_affected_validation",
        ]
    ].to_dict("records")

    log.info("Phase 3: sensor forensics")
    shift_summary = sensor_shift_summary(m, sc, facts["features"])
    shift_summary.to_parquet(out / "sensor_shift_summary.parquet", index=False)
    quality = sensor_quality_diagnostics(m, facts["features"])
    quality.to_parquet(out / "sensor_quality_diagnostics.parquet", index=False)
    qflags = quality[
        (quality["window"] != "train")
        & quality[
            [
                "frozen_suspect",
                "offset_suspect",
                "variance_collapse",
                "variance_explosion",
                "saturation_suspect",
                "missingness_spike",
            ]
        ].any(axis=1)
    ]
    findings["sensor_quality_flags"] = qflags[
        [
            "sensor",
            "window",
            "frozen_suspect",
            "offset_suspect",
            "variance_collapse",
            "variance_explosion",
            "saturation_suspect",
            "missingness_spike",
        ]
    ].to_dict("records")
    sep = shift_summary[shift_summary["window"] == "validation_sep"]
    findings["top_sensor_shifts_sep"] = (
        sep.sort_values("abs_median_shift", ascending=False)[
            [
                "sensor",
                "median",
                "abs_median_shift",
                "rel_median_shift",
                "std_change_ratio",
                "evidence_count_validation",
            ]
        ]
        .head(8)
        .to_dict("records")
    )

    log.info("Phase 4: correlation shift")
    corr_ranked, corr_diag = correlation_shift_ranked(corr_dir, m, labels)
    corr_ranked.to_parquet(out / "correlation_shift_ranked.parquet", index=False)
    findings["correlation"] = corr_diag
    steam_pair = corr_ranked[
        (corr_ranked["feature_a"] == "steam_valve_pressure_me2")
        & (corr_ranked["feature_b"] == "conditioner_steam_loop_temp")
        | (corr_ranked["feature_b"] == "steam_valve_pressure_me2")
        & (corr_ranked["feature_a"] == "conditioner_steam_loop_temp")
    ]
    findings["correlation"]["steam_pair_example"] = steam_pair[
        [
            "profile",
            "pearson_train",
            "pearson_validation",
            "spearman_train",
            "spearman_validation",
        ]
    ].to_dict("records")
    findings["correlation"]["top_shifts"] = corr_ranked.head(8)[
        [
            "profile",
            "feature_a",
            "feature_b",
            "pearson_train",
            "pearson_validation",
            "sign_flip_pearson",
            "involves_steam",
        ]
    ].to_dict("records")

    log.info("Phase 5: PCA forensics")
    pca_summary, pca_daily = pca_diagnostics(pca_dir, facts)
    pca_summary.to_parquet(out / "pca_diagnostic_summary.parquet", index=False)
    findings["pca"] = pca_summary[
        [
            "profile",
            "q_median_train",
            "q_median_validation",
            "q_ks_statistic",
            "share_validation_above_q_threshold",
            "top3_validation_contributors",
            "top3_contribution_share",
        ]
    ].to_dict("records")

    log.info("Phase 6: detector agreement")
    agr_summary, agr_by_profile, agr_diag = detector_agreement(sc, anom_dir)
    agr_summary.to_parquet(out / "detector_agreement_summary.parquet", index=False)
    agr_by_profile.to_parquet(
        out / "detector_agreement_by_profile.parquet", index=False
    )
    findings["agreement"] = agr_diag
    val_agr = agr_summary[(agr_summary["window"] == "validation")]
    findings["agreement"]["validation_rates"] = val_agr[
        val_agr["detector_set"].isin(
            [*DETECTORS, "ALL4_FAMILY", "ALL5", "TRIPLE_OR_MORE"]
        )
    ][["detector_set", "rate"]].to_dict("records")

    log.info("Phase 7: change-point candidates")
    cands = change_point_candidates(
        daily, sc, m, pca_daily, facts["features"], facts["train_end"]
    )
    cands.to_parquet(out / "change_point_candidates.parquet", index=False)
    findings["change_points"] = cands.head(10).to_dict("records")

    log.info("Phase 8: top-event review pack")
    pack = top_events_review(sc, findings["timeline"]["first_sustained_day"], quality)
    pack.to_parquet(out / "top_events_review.parquet", index=False)
    findings["review_pack"] = {
        "n_events": len(pack),
        "categories": sorted(pack["category"].unique()),
    }

    log.info("Phase 9: figures")
    figures = make_figures(
        out, daily, dbp, m, pca_daily, cands, shift_summary, facts["train_end"]
    )
    findings["figures"] = figures

    _write_json(out / "artifact_inventory.json", inventory)
    write_limitations(out, findings)
    _write_json(out / "findings.json", findings)
    print("\n===== FINDINGS =====")
    print(json.dumps(findings, indent=2, default=str))
    print(f"\nForensic run directory: {out}")
    print(
        "NOTE: manifest not yet written — add executive_summary.md, then run --finalize",
        run_id,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--finalize",
        metavar="RUN_ID",
        default=None,
        help="Write forensic_manifest.json (last) for an existing run.",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=args.log_level, format="%(levelname)s %(name)s: %(message)s"
    )
    if args.finalize:
        finalize_manifest(args.finalize)
        return 0
    return run_analysis()


if __name__ == "__main__":
    sys.exit(main())
