// Incidents Intelligence domain types consumed by the /incidents view.
// Presentation components (KPI cards, severity chart, incident list) consume
// these shapes; data sources (demo fixtures today, backend JSON later) produce them.

export type IncidentSeverity = "normal" | "warning" | "critical";

export type IncidentStatus = "open" | "in_review" | "contextualised" | "closed";

export interface IncidentKpi {
  label: string;
  value: string | number;
  description?: string;
}

export interface IncidentSeverityDistributionItem {
  severity: IncidentSeverity;
  label: string;
  count: number;
}

export interface IncidentRecord {
  id: string;
  title: string;
  severity: IncidentSeverity;
  status: IncidentStatus;
  startDate: string;
  endDate: string;
  affectedSignals: string[];
  evidenceSummary: string;
  recommendation: string;
}

export interface IncidentInsight {
  title: string;
  body: string;
}

export interface IncidentsSummary {
  assetName: string;
  datasetName: string;
  periodStart: string;
  periodEnd: string;
  summaryKpis: IncidentKpi[];
  severityDistribution: IncidentSeverityDistributionItem[];
  incidents: IncidentRecord[];
  insights: IncidentInsight[];
}
