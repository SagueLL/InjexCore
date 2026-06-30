// TEMPORARY frontend demo data for the Incidents page.
//
// This is NOT the source of truth. It exists only to build and preview the UI
// before the backend exists, and will be replaced by backend-generated dashboard
// JSON / API data (the Intelligence Layer output) once that contract is wired up.
// Do not depend on these exact values beyond local UI development.

import type { IncidentsSummary } from "@/types/incidents";

export const demoIncidentsSummary: IncidentsSummary = {
  assetName: "Pelletizer line",
  datasetName: "Real industrial dataset",
  periodStart: "2024-06-14",
  periodEnd: "2024-09-03",
  summaryKpis: [
    {
      label: "Total incidents",
      value: 17,
      description: "Grouped evidence windows raised for review.",
    },
    {
      label: "Critical incidents",
      value: 4,
      description: "Highest-priority windows to review first.",
    },
    {
      label: "Open review",
      value: 6,
      description: "Awaiting operator and production context.",
    },
    {
      label: "Contextualised",
      value: 11,
      description: "Explained by sensor quality or known operating conditions.",
    },
  ],
  severityDistribution: [
    { severity: "critical", label: "Critical", count: 4 },
    { severity: "warning", label: "Warning", count: 9 },
    { severity: "normal", label: "Normal", count: 4 },
  ],
  incidents: [
    {
      id: "INC-001",
      title: "Residual anomaly concentration",
      severity: "critical",
      status: "in_review",
      startDate: "2024-08-29",
      endDate: "2024-09-03",
      affectedSignals: ["Motor current", "Pelletizer load"],
      evidenceSummary:
        "A dense cluster of anomaly evidence persisting toward the end of the analysed window. Grouped as a single review candidate rather than a confirmed failure.",
      recommendation:
        "Review against operator logs and production schedule before any action; treat as an evidence window to investigate first.",
    },
    {
      id: "INC-002",
      title: "Sustained drift window",
      severity: "warning",
      status: "contextualised",
      startDate: "2024-07-12",
      endDate: "2024-07-19",
      affectedSignals: ["Feeder speed", "Screw pressure"],
      evidenceSummary:
        "Gradual operational drift across several days. Partly aligned with a known production-rate change, so the evidence is candidate drift, not a proven deviation.",
      recommendation:
        "Monitor and cross-check against the production schedule; no immediate action while the window remains explained by operating conditions.",
    },
    {
      id: "INC-003",
      title: "Load-related deviation",
      severity: "warning",
      status: "open",
      startDate: "2024-08-05",
      endDate: "2024-08-08",
      affectedSignals: ["Pelletizer load", "Motor current"],
      evidenceSummary:
        "Deviation evidence that coincides with load changes. May be related to throughput rather than machine condition; relationship is associative only.",
      recommendation:
        "Confirm against production-rate changes with the operator before drawing conclusions.",
    },
    {
      id: "INC-004",
      title: "Sensor-quality affected anomaly",
      severity: "critical",
      status: "in_review",
      startDate: "2024-08-20",
      endDate: "2024-09-03",
      affectedSignals: ["Hopper temperature"],
      evidenceSummary:
        "Anomaly evidence overlapping a sensor-quality issue on the same signal, so process attribution is uncertain. Likely sensor-dominated rather than a machine event.",
      recommendation:
        "Quarantine of the affected channel is pending review and human approval — the channel is not excluded automatically. Verify sensor reliability before interpreting as a process fault.",
    },
    {
      id: "INC-005",
      title: "Cooling instability evidence",
      severity: "warning",
      status: "contextualised",
      startDate: "2024-06-28",
      endDate: "2024-07-02",
      affectedSignals: ["Cooling water temperature", "Main drive vibration"],
      evidenceSummary:
        "Intermittent cooling instability evidence grouped into one window. Temporally associated with a maintenance period already on record.",
      recommendation:
        "Review alongside maintenance records; keep as a low-priority candidate while the context holds.",
    },
    {
      id: "INC-006",
      title: "Low-severity drift evidence",
      severity: "normal",
      status: "closed",
      startDate: "2024-06-15",
      endDate: "2024-06-16",
      affectedSignals: ["Hopper temperature"],
      evidenceSummary:
        "Minor drift evidence within expected operating variation. Reviewed, contextualised and closed with no further action required.",
      recommendation:
        "No action needed; retained as a reference example of normal operational variation.",
    },
  ],
  insights: [
    {
      title: "Incidents are reviewable evidence windows",
      body:
        "Incidents group anomaly and drift evidence into a small number of reviewable windows, so operators look at consolidated episodes instead of thousands of raw readings.",
    },
    {
      title: "Severity prioritises review",
      body:
        "Severity ranks where to look first; it reflects review priority, not confirmed failure impact. A critical label means investigate early, not that a breakdown is certain.",
    },
    {
      title: "Context is required before action",
      body:
        "Operator and production context is required before acting on any incident. Relationships between incidents are associative, not causal, and quarantine recommendations stay pending human approval.",
    },
  ],
};
