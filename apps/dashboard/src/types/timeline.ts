export type TimelineStatus = "normal" | "warning" | "drift" | "critical";

export type TimelineEventType =
  | "baseline"
  | "warning"
  | "drift"
  | "incident"
  | "review";

export type TimelineSeverity = "normal" | "warning" | "critical";

export interface TimelineSummaryKpi {
  label: string;
  value: string | number;
  description?: string;
}

export interface TimelinePoint {
  date: string;
  deviationScore: number;
  incidentCount: number;
  status: TimelineStatus;
}

export interface TimelineEvent {
  date: string;
  type: TimelineEventType;
  severity: TimelineSeverity;
  title: string;
  description: string;
}

export interface TimelinePeriod {
  title: string;
  startDate: string;
  endDate: string;
  status: TimelineStatus;
  description: string;
}

export interface OperationalTimeline {
  assetName: string;
  datasetName: string;
  periodStart: string;
  periodEnd: string;
  summaryKpis: TimelineSummaryKpi[];
  series: TimelinePoint[];
  periods: TimelinePeriod[];
  events: TimelineEvent[];
}
