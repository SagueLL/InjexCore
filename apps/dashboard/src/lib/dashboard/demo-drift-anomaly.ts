// TEMPORARY frontend demo data for the Drift & Anomaly Intelligence page.
//
// This is NOT the source of truth. It exists only to build and preview the UI
// before the backend exists, and will be replaced by backend-generated dashboard
// JSON / API data (the Intelligence Layer drift/anomaly output) once that contract
// is wired up. Do not depend on these exact values beyond local UI development.

import type { DriftAnomalySummary } from "@/types/drift-anomaly";

export const demoDriftAnomalySummary: DriftAnomalySummary = {
  assetName: "Pelletizer line",
  datasetName: "Real industrial dataset",
  periodStart: "2024-06-14",
  periodEnd: "2024-09-03",
  summaryKpis: [
    {
      label: "Raw non-normal windows",
      value: "33,186",
      description: "Windows flagged before operational context is applied.",
    },
    {
      label: "Contextualised anomalies",
      value: "30,096",
      description: "Explained by operational context (state, recipe, BOM).",
    },
    {
      label: "Residual review",
      value: "3,090",
      description: "Remaining evidence after context-aware filtering.",
    },
    {
      label: "Healthy-only drift windows",
      value: 23,
      description: "Drift windows that persist on healthy signals only.",
    },
  ],
  // Sampled chronological markers (not a daily sum). Anomaly evidence stays low in
  // June, rises through July, and is strongest in late August / early September.
  // residualCount stays well below anomalyCount to reflect context-aware filtering.
  evidenceSeries: [
    {
      date: "2024-06-14",
      evidenceShare: 0.08,
      anomalyCount: 120,
      residualCount: 14,
      severity: "normal",
    },
    {
      date: "2024-06-28",
      evidenceShare: 0.12,
      anomalyCount: 210,
      residualCount: 22,
      severity: "normal",
    },
    {
      date: "2024-07-12",
      evidenceShare: 0.24,
      anomalyCount: 540,
      residualCount: 61,
      severity: "warning",
    },
    {
      date: "2024-07-26",
      evidenceShare: 0.33,
      anomalyCount: 890,
      residualCount: 102,
      severity: "warning",
    },
    {
      date: "2024-08-09",
      evidenceShare: 0.41,
      anomalyCount: 1320,
      residualCount: 158,
      severity: "warning",
    },
    {
      date: "2024-08-19",
      evidenceShare: 0.55,
      anomalyCount: 2240,
      residualCount: 240,
      severity: "warning",
    },
    {
      date: "2024-08-26",
      evidenceShare: 0.72,
      anomalyCount: 3680,
      residualCount: 360,
      severity: "critical",
    },
    {
      date: "2024-08-31",
      evidenceShare: 0.86,
      anomalyCount: 4920,
      residualCount: 430,
      severity: "critical",
    },
    {
      date: "2024-09-03",
      evidenceShare: 0.91,
      anomalyCount: 5360,
      residualCount: 470,
      severity: "critical",
    },
  ],
  detectionMethods: [
    {
      method: "isolation_forest",
      label: "Isolation Forest",
      evidenceCount: 12480,
      description: "Flags windows that are easy to isolate from normal behaviour.",
    },
    {
      method: "lof",
      label: "Local Outlier Factor (LOF)",
      evidenceCount: 9870,
      description: "Detects points that are sparse relative to their neighbours.",
    },
    {
      method: "ocsvm",
      label: "One-Class SVM",
      evidenceCount: 7320,
      description: "Learns a boundary around normal operation and flags outliers.",
    },
    {
      method: "pca_residual",
      label: "PCA residual",
      evidenceCount: 6450,
      description: "Highlights windows that break normal signal correlations.",
    },
    {
      method: "context_overlay",
      label: "Operational context overlay",
      evidenceCount: 30096,
      description: "Reclassifies raw anomalies that operational context explains.",
    },
  ],
  affectedSignals: [
    {
      sensorId: "motor_current",
      displayName: "Motor current",
      contribution: "high",
      severity: "critical",
      interpretation: "Sustained current rise tracks the late-August evidence peak.",
    },
    {
      sensorId: "main_drive_vibration",
      displayName: "Main drive vibration",
      contribution: "high",
      severity: "critical",
      interpretation: "Vibration spread widens alongside the strongest anomaly windows.",
    },
    {
      sensorId: "feeder_speed",
      displayName: "Feeder speed",
      contribution: "high",
      severity: "warning",
      interpretation: "Feed-rate swings increase from July onward and need review.",
    },
    {
      sensorId: "hopper_temperature",
      displayName: "Hopper temperature",
      contribution: "medium",
      severity: "warning",
      interpretation: "Gradual upward drift, partly explained by ambient context.",
    },
    {
      sensorId: "cooling_water_temperature",
      displayName: "Cooling water temperature",
      contribution: "medium",
      severity: "warning",
      interpretation: "Cooling deviations coincide with higher load periods.",
    },
    {
      sensorId: "screw_pressure",
      displayName: "Screw pressure",
      contribution: "low",
      severity: "normal",
      interpretation: "Minor variation only; no sustained deviation observed.",
    },
  ],
  insights: [
    {
      title: "Context-aware filtering reduced raw anomaly volume",
      body: "Operational context explained most raw windows, narrowing 33,186 non-normal windows down to 3,090 for residual review.",
    },
    {
      title: "Review residual evidence by period and affected signal",
      body: "Remaining evidence concentrates in late August / early September and on a few signals — review it by period and affected signal rather than as a single total.",
    },
    {
      title: "Decision support, not a replacement for operator judgement",
      body: "Drift and anomaly intelligence highlights where to look and surfaces evidence; it supports investigation and does not replace operator judgement.",
    },
  ],
};
