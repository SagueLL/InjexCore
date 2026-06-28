// Core dashboard domain types shared across the Executive Overview and related
// dashboard views. Presentation components (kpi-card, insight-card, status-badge)
// consume these shapes; data sources (demo fixtures today, backend JSON later)
// produce them.

export type OperationalStatus = "normal" | "warning" | "critical" | "unknown";

export interface DashboardKpi {
  label: string;
  value: string | number;
  description?: string;
  helperText?: string;
}

export interface ExecutiveInsight {
  title: string;
  body: string;
  footer?: string;
}

export interface DashboardSummary {
  assetName: string;
  datasetName: string;
  periodStart: string;
  periodEnd: string;
  totalRecords: number;
  operationalStatus: OperationalStatus;
  kpis: DashboardKpi[];
  executiveInsights: ExecutiveInsight[];
  limitations: string[];
}
