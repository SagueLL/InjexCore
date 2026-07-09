// TEMPORARY frontend demo data for the Operational Timeline view.
//
// This is NOT the source of truth. It exists only to build and preview the UI
// before the backend exists, and will be replaced by backend-generated dashboard
// JSON / API data (the Intelligence Layer output) once that contract is wired up.
// Do not depend on these exact values beyond local UI development.

import type { OperationalTimeline } from "@/types/timeline";

export const demoOperationalTimeline: OperationalTimeline = {
  assetName: "Pelletizer line",
  datasetName: "Real industrial dataset",
  periodStart: "2024-06-14",
  periodEnd: "2024-09-03",
  summaryKpis: [
    { label: "Analysed period", value: "82 days" },
    { label: "Incident windows", value: 17 },
    { label: "Drift periods", value: 4 },
    { label: "Highest risk period", value: "Late Aug" },
  ],
  series: [
    { date: "2024-06-14", evidenceShare: 0.08, incidentCount: 0, status: "normal" },
    { date: "2024-06-24", evidenceShare: 0.11, incidentCount: 0, status: "normal" },
    { date: "2024-07-04", evidenceShare: 0.18, incidentCount: 1, status: "normal" },
    { date: "2024-07-15", evidenceShare: 0.29, incidentCount: 2, status: "warning" },
    { date: "2024-07-26", evidenceShare: 0.38, incidentCount: 3, status: "warning" },
    { date: "2024-08-05", evidenceShare: 0.52, incidentCount: 4, status: "drift" },
    { date: "2024-08-15", evidenceShare: 0.64, incidentCount: 5, status: "drift" },
    { date: "2024-08-26", evidenceShare: 0.81, incidentCount: 6, status: "critical" },
    { date: "2024-09-03", evidenceShare: 0.74, incidentCount: 5, status: "drift" },
  ],
  periods: [
    {
      title: "Stable baseline",
      startDate: "2024-06-14",
      endDate: "2024-07-08",
      status: "normal",
      description:
        "Low, stable deviation. The line operates inside its expected operational envelope.",
    },
    {
      title: "Deviation build-up",
      startDate: "2024-07-09",
      endDate: "2024-08-04",
      status: "warning",
      description:
        "Deviation rises steadily and early warning signals begin to appear across several signals.",
    },
    {
      title: "Main drift concentration",
      startDate: "2024-08-05",
      endDate: "2024-09-03",
      status: "drift",
      description:
        "Sustained operational drift, with the strongest evidence concentrated in late August.",
    },
  ],
  events: [
    {
      date: "2024-06-14",
      type: "baseline",
      severity: "normal",
      title: "Analysis window starts",
      description:
        "Baseline established. The line operates within its expected operational envelope.",
    },
    {
      date: "2024-07-15",
      type: "warning",
      severity: "warning",
      title: "First deviation build-up",
      description:
        "Early operational deviation begins to appear in the monitored signals.",
    },
    {
      date: "2024-08-05",
      type: "drift",
      severity: "warning",
      title: "Sustained drift begins",
      description:
        "Deviation becomes persistent across multiple signals rather than isolated.",
    },
    {
      date: "2024-08-26",
      type: "incident",
      severity: "critical",
      title: "Highest evidence concentration",
      description:
        "The strongest anomaly and drift evidence concentrates in late August.",
    },
    {
      date: "2024-09-03",
      type: "review",
      severity: "warning",
      title: "Review required",
      description:
        "Analysis window ends. The late-August period is flagged for engineering review.",
    },
  ],
};
