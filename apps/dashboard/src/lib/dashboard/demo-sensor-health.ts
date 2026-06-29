// TEMPORARY frontend demo data for the Sensor Health Intelligence page.
//
// This is NOT the source of truth. It exists only to build and preview the UI
// before the backend exists, and will be replaced by backend-generated dashboard
// JSON / API data (the Intelligence Layer sensor-health output) once that contract
// is wired up. Do not depend on these exact values beyond local UI development.

import type { SensorHealthSummary } from "@/types/sensor-health";

export const demoSensorHealthSummary: SensorHealthSummary = {
  assetName: "Pelletizer line",
  datasetName: "Real industrial dataset",
  periodStart: "2024-06-14",
  periodEnd: "2024-09-03",
  summaryKpis: [
    {
      label: "Healthy signals",
      value: 16,
      description: "Stable, well-covered signals.",
    },
    {
      label: "Warning signals",
      value: 4,
      description: "Reliability concerns to monitor.",
    },
    {
      label: "Critical signals",
      value: 2,
      description: "Unreliable instrumentation; not decision-grade alone.",
    },
    {
      label: "Review required",
      value: 6,
      description: "Signals flagged warning or critical.",
    },
  ],
  distribution: [
    { status: "healthy", label: "Healthy", count: 16 },
    { status: "warning", label: "Warning", count: 4 },
    { status: "critical", label: "Critical", count: 2 },
    { status: "unknown", label: "Unknown", count: 2 },
  ],
  problematicSignals: [
    {
      sensorId: "hopper_temp",
      displayName: "Hopper temperature",
      status: "critical",
      coveragePct: 41.2,
      issueTypes: ["frozen_signal", "low_coverage"],
      recommendation:
        "Flatlined for extended windows; inspect wiring and exclude from automated scoring until verified.",
    },
    {
      sensorId: "cooling_water_temp",
      displayName: "Cooling water temperature",
      status: "critical",
      coveragePct: 53.8,
      issueTypes: ["missing_values", "low_coverage"],
      recommendation:
        "High missing-data ratio; verify the acquisition channel before using in anomaly interpretation.",
    },
    {
      sensorId: "main_drive_vibration",
      displayName: "Main drive vibration",
      status: "warning",
      coveragePct: 91.4,
      issueTypes: ["noise", "outlier_spikes"],
      recommendation:
        "Elevated noise and intermittent spikes; corroborate with redundant signals before flagging incidents.",
    },
    {
      sensorId: "motor_current",
      displayName: "Motor current",
      status: "warning",
      coveragePct: 96.7,
      issueTypes: ["drift"],
      recommendation:
        "Gradual baseline shift; monitor and cross-check against maintenance records.",
    },
    {
      sensorId: "feeder_speed",
      displayName: "Feeder speed",
      status: "warning",
      coveragePct: 94.2,
      issueTypes: ["outlier_spikes"],
      recommendation:
        "Occasional spikes likely operational; keep under observation.",
    },
    {
      sensorId: "screw_pressure",
      displayName: "Screw pressure",
      status: "warning",
      coveragePct: 93.0,
      issueTypes: ["noise"],
      recommendation:
        "Increased signal noise; smooth before trend analysis.",
    },
  ],
  insights: [
    {
      title: "Signal reliability shapes anomaly interpretation",
      body: "Unreliable sensors can distort how deviations and incidents are read. Signal coverage and stability are weighed alongside the anomaly scores, not after them.",
    },
    {
      title: "Critical signals are not decision-grade alone",
      body: "Signals flagged critical should not drive automated decisions on their own. Treat them as evidence that requires corroboration and human review.",
    },
    {
      title: "Sensor health review reduces false positives",
      body: "Auditing instrumentation reliability filters out noise- and dropout-driven false alarms and builds trust in the intelligence layer.",
    },
  ],
};
