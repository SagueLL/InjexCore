// TEMPORARY frontend demo data for the Executive Overview page.
//
// This is NOT the source of truth. It exists only to build and preview the UI
// before the backend exists, and will be replaced by backend-generated dashboard
// JSON / API data (the Intelligence Layer output) once that contract is wired up.
// Do not depend on these exact values beyond local UI development.

import type { DashboardSummary } from "@/types/dashboard";

export const demoOverviewSummary: DashboardSummary = {
  assetName: "Pelletizer line",
  datasetName: "Real industrial dataset",
  periodStart: "2024-06-14",
  periodEnd: "2024-09-03",
  totalRecords: 167331,
  operationalStatus: "warning",
  kpis: [
    { label: "Analysed records", value: "167,331" },
    { label: "Detected incidents", value: 17 },
    { label: "Problematic sensors", value: 23 },
    { label: "Contextualised anomalies", value: "30,096" },
  ],
  executiveInsights: [
    {
      title: "Main operational finding",
      body:
        "Across 167,331 historical records, recurring deviations were aggregated into 17 distinct incidents, several clustered in the same operating periods. These mark early operational drift worth reviewing first — anomaly evidence to guide maintenance triage, not guaranteed failures.",
      footer: "Period analysed: 14 Jun – 3 Sep 2024.",
    },
    {
      title: "Sensor reliability matters",
      body:
        "23 sensors showed unreliable behaviour, including an inlet-hopper channel flatlined at zero. About 30,096 anomalies were contextualised as sensor-dominated rather than process events and down-weighted, so signal-quality issues are not mistaken for machine faults. Reliable conclusions depend on first separating sensor reliability from genuine operational behaviour.",
    },
    {
      title: "Best current use",
      body:
        "Today this is most useful as an offline forensic and triage aid: it ranks incidents and sensors on operational evidence to show where to look first. It supports engineering judgement rather than replacing it, and does not predict exact failures or their timing.",
      footer: "Offline historical analysis — decision support, not autonomous control.",
    },
  ],
  limitations: [
    "Offline historical analysis, not real-time monitoring.",
    "Anomalies are operational evidence, not guaranteed failures.",
    "Pelletizer data demonstrates the intelligence layer but is not yet the final commercial pilot cell.",
  ],
};
