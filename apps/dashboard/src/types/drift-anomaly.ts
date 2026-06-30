// Drift & Anomaly Intelligence domain types consumed by the /drift-anomaly view.
// Presentation components (KPI cards, anomaly evidence chart, detection-method and
// affected-signal panels) consume these shapes; data sources (demo fixtures today,
// backend JSON later) produce them.

export type DriftAnomalySeverity = "normal" | "warning" | "critical";

export type DetectionMethod =
  | "isolation_forest"
  | "lof"
  | "ocsvm"
  | "pca_residual"
  | "context_overlay";

export type ContributionLevel = "low" | "medium" | "high";

export interface DriftAnomalyKpi {
  label: string;
  value: string | number;
  description?: string;
}

export interface AnomalyEvidencePoint {
  date: string;
  anomalyScore: number;
  anomalyCount: number;
  residualCount: number;
  severity: DriftAnomalySeverity;
}

export interface DetectionMethodSummary {
  method: DetectionMethod;
  label: string;
  evidenceCount: number;
  description: string;
}

export interface AffectedSignal {
  sensorId: string;
  displayName: string;
  contribution: ContributionLevel;
  severity: DriftAnomalySeverity;
  interpretation: string;
}

export interface DriftAnomalyInsight {
  title: string;
  body: string;
}

export interface DriftAnomalySummary {
  assetName: string;
  datasetName: string;
  periodStart: string;
  periodEnd: string;
  summaryKpis: DriftAnomalyKpi[];
  evidenceSeries: AnomalyEvidencePoint[];
  detectionMethods: DetectionMethodSummary[];
  affectedSignals: AffectedSignal[];
  insights: DriftAnomalyInsight[];
}
