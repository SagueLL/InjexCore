// Sensor Health Intelligence domain types consumed by the /sensor-health view.
// Presentation components (KPI cards, distribution chart, signals table) consume
// these shapes; data sources (demo fixtures today, backend JSON later) produce them.

export type SensorHealthStatus = "healthy" | "warning" | "critical" | "unknown";

export type SensorIssueType =
  | "low_coverage"
  | "noise"
  | "frozen_signal"
  | "drift"
  | "outlier_spikes"
  | "missing_values";

export interface SensorHealthKpi {
  label: string;
  value: string | number;
  description?: string;
}

export interface SensorHealthDistributionItem {
  status: SensorHealthStatus;
  label: string;
  count: number;
}

export interface SensorHealthSignal {
  sensorId: string;
  displayName: string;
  status: SensorHealthStatus;
  coveragePct: number;
  issueTypes: SensorIssueType[];
  recommendation: string;
}

export interface SensorHealthInsight {
  title: string;
  body: string;
}

export interface SensorHealthSummary {
  assetName: string;
  datasetName: string;
  periodStart: string;
  periodEnd: string;
  summaryKpis: SensorHealthKpi[];
  distribution: SensorHealthDistributionItem[];
  problematicSignals: SensorHealthSignal[];
  insights: SensorHealthInsight[];
}
