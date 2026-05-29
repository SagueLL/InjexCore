"""Temporal quality analysis of data/raw/Dades_pellet.csv.

Streams the CSV (stdlib only, ~167k rows) and computes metrics that answer
the temporal-comprehension questions: sampling cadence, jitter, gaps,
monotonicity, duplicates, drift in cadence, per-column synchronization
(NaN co-occurrence), and machine-idle periods.

Outputs:
  - data/features/temporal_quality_report.json  (raw findings)
  - data/features/temporal_questions.csv        (questions + importance + finding)
"""
from __future__ import annotations

import csv
import json
import statistics
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "data" / "raw" / "Dades_pellet.csv"
OUT_DIR = PROJECT_ROOT / "data" / "features"
REPORT_PATH = OUT_DIR / "temporal_quality_report.json"
QUESTIONS_PATH = OUT_DIR / "temporal_questions.csv"

TS_FORMAT = "%Y-%m-%d %H:%M:%S.%f"
EXPECTED_PERIOD_S = 60.0  # 1 minute, confirmed from EDA
GAP_FACTOR = 2.0          # delta > GAP_FACTOR * expected_period → gap


def parse_ts(s: str) -> datetime | None:
    s = s.strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, TS_FORMAT)
    except ValueError:
        try:
            return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None


def is_missing(v: str) -> bool:
    v = v.strip()
    return v == "" or v.lower() in {"nan", "null", "none"}


def main() -> None:
    deltas_s: list[float] = []
    timestamps: list[datetime] = []
    rows_total = 0
    rows_bad_ts = 0
    rows_out_of_order = 0
    duplicates = 0
    gaps: list[tuple[str, str, float]] = []  # (prev_ts, this_ts, delta_s)

    prev_ts: datetime | None = None
    per_col_nan_counts: list[int] = []
    per_col_nan_runs: list[int] = []   # longest consecutive NaN run per column
    per_col_current_run: list[int] = []
    col_codes: list[str] = []
    col_descriptions: list[str] = []

    # Co-missingness: count rows where all process-numeric cols are simultaneously missing.
    rows_all_numeric_missing = 0
    rows_any_numeric_missing = 0

    with SRC.open("r", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        descriptions_es = next(reader)
        codes = next(reader)
        units = next(reader)
        col_codes = [c.strip() for c in codes]
        col_descriptions = [d.strip() for d in descriptions_es]
        n_cols = len(codes)
        per_col_nan_counts = [0] * n_cols
        per_col_nan_runs = [0] * n_cols
        per_col_current_run = [0] * n_cols

        # Numeric columns: everything except the timestamp (idx 0), the 4 ID cols (1-4),
        # and the unitless rows. We treat indices 5..36 as "signal" columns.
        signal_cols = list(range(5, n_cols))

        for row in reader:
            rows_total += 1
            if len(row) < n_cols:
                row = row + [""] * (n_cols - len(row))

            ts = parse_ts(row[0])
            if ts is None:
                rows_bad_ts += 1
            else:
                if prev_ts is not None:
                    delta = (ts - prev_ts).total_seconds()
                    deltas_s.append(delta)
                    if delta < 0:
                        rows_out_of_order += 1
                    elif delta == 0:
                        duplicates += 1
                    elif delta > GAP_FACTOR * EXPECTED_PERIOD_S:
                        gaps.append((
                            prev_ts.strftime(TS_FORMAT)[:-3],
                            ts.strftime(TS_FORMAT)[:-3],
                            round(delta, 3),
                        ))
                prev_ts = ts
                timestamps.append(ts)

            # Per-column missingness
            missing_signal = 0
            for i in range(n_cols):
                if is_missing(row[i]):
                    per_col_nan_counts[i] += 1
                    per_col_current_run[i] += 1
                    if per_col_current_run[i] > per_col_nan_runs[i]:
                        per_col_nan_runs[i] = per_col_current_run[i]
                    if i in signal_cols:
                        missing_signal += 1
                else:
                    per_col_current_run[i] = 0

            if missing_signal == len(signal_cols):
                rows_all_numeric_missing += 1
            if missing_signal > 0:
                rows_any_numeric_missing += 1

    # --- Aggregate metrics ---
    n_deltas = len(deltas_s)
    median_delta = statistics.median(deltas_s) if deltas_s else 0.0
    mean_delta = statistics.mean(deltas_s) if deltas_s else 0.0
    stdev_delta = statistics.stdev(deltas_s) if n_deltas > 1 else 0.0
    min_delta = min(deltas_s) if deltas_s else 0.0
    max_delta = max(deltas_s) if deltas_s else 0.0
    # Percentiles via sorted list
    sorted_deltas = sorted(deltas_s)
    def pct(p: float) -> float:
        if not sorted_deltas:
            return 0.0
        k = max(0, min(len(sorted_deltas) - 1, int(round(p * (len(sorted_deltas) - 1)))))
        return sorted_deltas[k]
    p01 = pct(0.01); p05 = pct(0.05); p50 = pct(0.50); p95 = pct(0.95); p99 = pct(0.99)
    jitter_iqr = pct(0.75) - pct(0.25)

    # Cadence drift: split deltas into 10 equal chunks, compare medians
    drift_segments: list[dict] = []
    if n_deltas >= 100:
        chunk = n_deltas // 10
        for i in range(10):
            seg = deltas_s[i * chunk : (i + 1) * chunk if i < 9 else n_deltas]
            drift_segments.append({
                "segment": i,
                "n": len(seg),
                "median_s": round(statistics.median(seg), 4),
                "mean_s": round(statistics.mean(seg), 4),
            })
    drift_range = (
        max(s["median_s"] for s in drift_segments) - min(s["median_s"] for s in drift_segments)
        if drift_segments else 0.0
    )

    # Total span
    first_ts = timestamps[0] if timestamps else None
    last_ts = timestamps[-1] if timestamps else None
    span_s = (last_ts - first_ts).total_seconds() if first_ts and last_ts else 0.0
    expected_rows_at_perfect_cadence = int(span_s / EXPECTED_PERIOD_S) + 1 if span_s else 0
    coverage_pct = round(100.0 * rows_total / expected_rows_at_perfect_cadence, 3) if expected_rows_at_perfect_cadence else 0.0

    # Per-column NaN summary (top offenders)
    per_col_summary = []
    for i in range(len(col_codes)):
        per_col_summary.append({
            "idx": i,
            "code": col_codes[i],
            "description": col_descriptions[i],
            "nan_count": per_col_nan_counts[i],
            "nan_pct": round(100.0 * per_col_nan_counts[i] / rows_total, 3) if rows_total else 0.0,
            "longest_nan_run": per_col_nan_runs[i],
        })
    top_nan_cols = sorted(per_col_summary, key=lambda d: d["nan_count"], reverse=True)[:10]

    # Gap summary
    n_gaps = len(gaps)
    total_gap_seconds = sum(g[2] - EXPECTED_PERIOD_S for g in gaps)  # excess over expected
    largest_gaps = sorted(gaps, key=lambda g: g[2], reverse=True)[:10]

    report = {
        "source": str(SRC.relative_to(PROJECT_ROOT)),
        "rows_total": rows_total,
        "rows_with_bad_timestamp": rows_bad_ts,
        "rows_out_of_order": rows_out_of_order,
        "duplicate_timestamps": duplicates,
        "first_timestamp": first_ts.strftime(TS_FORMAT)[:-3] if first_ts else None,
        "last_timestamp": last_ts.strftime(TS_FORMAT)[:-3] if last_ts else None,
        "span_seconds": span_s,
        "span_days": round(span_s / 86400, 3),
        "expected_period_s": EXPECTED_PERIOD_S,
        "cadence": {
            "median_s": round(median_delta, 4),
            "mean_s": round(mean_delta, 4),
            "stdev_s": round(stdev_delta, 4),
            "min_s": round(min_delta, 4),
            "max_s": round(max_delta, 4),
            "p01_s": round(p01, 4),
            "p05_s": round(p05, 4),
            "p50_s": round(p50, 4),
            "p95_s": round(p95, 4),
            "p99_s": round(p99, 4),
            "iqr_s": round(jitter_iqr, 4),
        },
        "coverage_pct_vs_perfect": coverage_pct,
        "expected_rows_at_perfect_cadence": expected_rows_at_perfect_cadence,
        "gaps": {
            "n_gaps_over_2x_expected": n_gaps,
            "total_excess_seconds": round(total_gap_seconds, 1),
            "largest_gaps_top10": [
                {"from": g[0], "to": g[1], "delta_s": g[2]} for g in largest_gaps
            ],
        },
        "cadence_drift": {
            "segments": drift_segments,
            "median_range_across_segments_s": round(drift_range, 4),
        },
        "synchronization": {
            "single_timestamp_column": True,
            "rows_with_any_signal_missing": rows_any_numeric_missing,
            "rows_with_all_signals_missing": rows_all_numeric_missing,
            "comment": (
                "All 37 columns share a single timestamp column (col 0), so row-level "
                "synchronization is guaranteed by construction. Per-sensor missingness "
                "(see top_nan_cols) reveals whether individual sensors drop out within rows."
            ),
        },
        "top_nan_columns": top_nan_cols,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with REPORT_PATH.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"Wrote {REPORT_PATH}")

    # --- Build the importance-ranked questions CSV using report findings ---
    questions = build_questions(report)
    with QUESTIONS_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["Question", "Importance", "Rationale", "Method", "Finding"],
        )
        writer.writeheader()
        writer.writerows(questions)
    print(f"Wrote {QUESTIONS_PATH} ({len(questions)} questions)")

    # Console summary
    print("\n--- Summary ---")
    print(f"Rows:                 {rows_total:,}")
    print(f"Span:                 {report['span_days']} days "
          f"({report['first_timestamp']} -> {report['last_timestamp']})")
    print(f"Median delta:         {report['cadence']['median_s']} s")
    print(f"Jitter (stdev):       {report['cadence']['stdev_s']} s")
    print(f"Min / Max delta:      {report['cadence']['min_s']} / {report['cadence']['max_s']} s")
    print(f"Coverage vs perfect:  {coverage_pct} %")
    print(f"Gaps > 2x expected:   {n_gaps}")
    print(f"Duplicates:           {duplicates}")
    print(f"Out-of-order:         {rows_out_of_order}")
    print(f"Bad timestamps:       {rows_bad_ts}")
    print(f"Cadence drift range:  {drift_range} s (median across 10 segments)")
    print(f"Rows with any signal NaN:  {rows_any_numeric_missing:,}")
    print(f"Rows with ALL signals NaN: {rows_all_numeric_missing:,}")


def build_questions(r: dict) -> list[dict[str, str]]:
    """Generate the ranked checklist from the report findings."""
    cad = r["cadence"]
    gaps = r["gaps"]
    drift = r["cadence_drift"]
    sync = r["synchronization"]
    expected = r["expected_period_s"]

    def fmt_jitter() -> str:
        return (
            f"Median={cad['median_s']}s, stdev={cad['stdev_s']}s, "
            f"IQR={cad['iqr_s']}s, min={cad['min_s']}s, max={cad['max_s']}s. "
            f"P5–P95: {cad['p05_s']}s–{cad['p95_s']}s"
        )

    return [
        {
            "Question": "Are all sensors synchronized to a common time base?",
            "Importance": "Very Critical",
            "Rationale": "Mismatched clocks invalidate cross-sensor models (lag features, correlations, anomaly co-occurrence). Whole pipeline breaks if false.",
            "Method": "Inspect whether columns share a single timestamp column; check per-sensor NaN co-occurrence.",
            "Finding": sync["comment"] + f" Rows with any signal NaN: {sync['rows_with_any_signal_missing']:,}; rows with ALL signals NaN: {sync['rows_with_all_signals_missing']:,}.",
        },
        {
            "Question": "Are timestamps monotonically increasing?",
            "Importance": "Critical",
            "Rationale": "Out-of-order rows corrupt lag/rolling features and forecasting splits; can mask real anomalies.",
            "Method": "Count consecutive deltas with negative value.",
            "Finding": f"{r['rows_out_of_order']} out-of-order row(s) found.",
        },
        {
            "Question": "Are there gaps in the time series?",
            "Importance": "Critical",
            "Rationale": "Gaps hide machine downtime or sensor loss; rolling-window features computed across gaps are wrong.",
            "Method": f"Count consecutive deltas > {GAP_FACTOR}x expected period ({GAP_FACTOR * expected:.0f}s).",
            "Finding": f"{gaps['n_gaps_over_2x_expected']} gap(s); cumulative excess time {gaps['total_excess_seconds']}s. Largest gap: {gaps['largest_gaps_top10'][0]['delta_s'] if gaps['largest_gaps_top10'] else 0}s.",
        },
        {
            "Question": "Are there duplicate timestamps?",
            "Importance": "Critical",
            "Rationale": "Duplicate rows can poison aggregations and forecasting models; often signals double-logging or clock stall.",
            "Method": "Count consecutive deltas equal to zero.",
            "Finding": f"{r['duplicate_timestamps']} duplicate timestamp(s) found.",
        },
        {
            "Question": "Do specific sensors fail (go NaN) over time?",
            "Importance": "Critical",
            "Rationale": "Per-sensor dropouts mean features collapse silently — model degrades on the affected sensor's contribution.",
            "Method": "Per-column NaN counts and longest-NaN-run.",
            "Finding": "Top offenders (NaN count): " + ", ".join(
                f"{c['code']}={c['nan_count']:,} ({c['nan_pct']}%, longest run={c['longest_nan_run']})"
                for c in r["top_nan_columns"][:5]
            ),
        },
        {
            "Question": "Is the sampling cadence stable (low jitter)?",
            "Importance": "Very High",
            "Rationale": "High jitter breaks the assumption of fixed-interval features (FFT, rolling-window stats) and biases forecasting.",
            "Method": "Stdev, IQR, and percentile spread of consecutive deltas.",
            "Finding": fmt_jitter(),
        },
        {
            "Question": "Is there temporal drift in the sampling cadence?",
            "Importance": "Very High",
            "Rationale": "Cadence drift causes silent shifts in temporal feature meaning across the dataset (a 1-min rolling mean today != 1-min rolling mean six months ago).",
            "Method": "Split deltas into 10 equal segments; compare segment medians.",
            "Finding": f"Range of segment-median deltas: {drift['median_range_across_segments_s']}s across 10 segments. Per-segment medians: " + ", ".join(f"{s['median_s']}s" for s in drift["segments"]),
        },
        {
            "Question": "What is the actual sampling frequency?",
            "Importance": "High",
            "Rationale": "Every downstream window/lag/decomposition choice depends on this. Wrong assumption → wrong features.",
            "Method": "Median of consecutive timestamp deltas.",
            "Finding": f"Median = {cad['median_s']}s (expected {expected}s, i.e. 1-minute). {cad['p50_s']}s at P50.",
        },
        {
            "Question": "What is the total observed time span and effective coverage?",
            "Importance": "High",
            "Rationale": "Determines whether dataset spans enough cycles, days, and operating regimes to train and validate models meaningfully.",
            "Method": "Last minus first timestamp; expected rows = span / expected_period.",
            "Finding": f"{r['span_days']} days from {r['first_timestamp']} to {r['last_timestamp']}. Coverage vs perfect 1-min cadence: {r['coverage_pct_vs_perfect']}% ({r['rows_total']:,} of {r['expected_rows_at_perfect_cadence']:,} expected rows).",
        },
        {
            "Question": "Are there long idle periods (machine off / no production)?",
            "Importance": "High",
            "Rationale": "Idle periods are not anomalies but contaminate anomaly-detection and energy/throughput regressions if not filtered.",
            "Method": "Use running flags (granulator_g2_running, feeder_al2_running) to segment active vs idle windows.",
            "Finding": "Not computed in this script (state-flag segmentation belongs to cycle/state analysis). See `detect-cycle-instability` for the next step.",
        },
        {
            "Question": "Are there malformed or unparseable timestamps?",
            "Importance": "High",
            "Rationale": "Silent parse failures drop rows and corrupt time-series indexing.",
            "Method": "Try-parse every row; count failures.",
            "Finding": f"{r['rows_with_bad_timestamp']} unparseable timestamp(s) on {r['rows_total']:,} rows.",
        },
        {
            "Question": "Do timestamps suggest time-zone / DST anomalies?",
            "Importance": "Medium",
            "Rationale": "DST shifts produce 1-hour gaps or duplicates twice a year — easy to mistake for sensor faults.",
            "Method": "Inspect timestamps near typical DST boundaries (last Sun of Mar / Oct) for ±1h jumps.",
            "Finding": "Largest gaps to review for DST: " + ", ".join(
                f"{g['from']}→{g['to']} ({g['delta_s']}s)" for g in gaps["largest_gaps_top10"][:3]
            ) if gaps["largest_gaps_top10"] else "No gaps recorded.",
        },
        {
            "Question": "Are there recurring periodic patterns (hourly / daily) in cadence or gaps?",
            "Importance": "Medium",
            "Rationale": "Periodic gaps may indicate scheduled maintenance, shift changes, or batch resets — important for evaluation splits.",
            "Method": "Bucket gaps by hour-of-day or day-of-week.",
            "Finding": "Not computed in this script. Recommend follow-up with detect-trend-and-seasonality on the gap timestamps.",
        },
        {
            "Question": "Is the data aligned at sub-second precision, and is precision uniform?",
            "Importance": "Low",
            "Rationale": "Millisecond timestamps suggest the source can guarantee tight sync; varying precision hints at multi-source merging.",
            "Method": "Inspect fractional-second part across the file.",
            "Finding": "Timestamps use millisecond precision (e.g., '2024-06-14 08:49:56.350'). Uniformity not formally tested.",
        },
    ]


if __name__ == "__main__":
    main()
