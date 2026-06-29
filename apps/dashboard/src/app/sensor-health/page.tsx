import { PageHeader } from "@/components/app/page-header";
import { ChartContainer } from "@/components/charts/chart-container";
import { SensorHealthDistributionChart } from "@/components/charts/sensor-health-distribution-chart";
import { KpiCard } from "@/components/dashboard/kpi-card";
import { SectionCard } from "@/components/dashboard/section-card";
import { StatusBadge } from "@/components/dashboard/status-badge";
import { demoSensorHealthSummary } from "@/lib/dashboard/demo-sensor-health";

import type { OperationalStatus } from "@/types/dashboard";
import type { SensorHealthStatus } from "@/types/sensor-health";

// StatusBadge speaks the operational-status vocabulary (normal/warning/critical/
// unknown); sensor health uses "healthy" instead of "normal". Map locally.
function toBadgeStatus(status: SensorHealthStatus): OperationalStatus {
  return status === "healthy" ? "normal" : status;
}

function humanizeIssueType(issueType: string): string {
  return issueType.replace(/_/g, " ");
}

export default function SensorHealthPage() {
  const sensorHealth = demoSensorHealthSummary;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Sensor Health Intelligence"
        description="Signal reliability and data quality overview for the analysed period."
      />

      <SectionCard
        title="Analysed context"
        description="Current sensor health scope and historical dataset."
      >
        <dl className="grid grid-cols-1 gap-x-8 gap-y-2 sm:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-0.5">
            <dt className="text-xs text-muted-foreground">Asset</dt>
            <dd className="text-sm font-medium text-foreground">
              {sensorHealth.assetName}
            </dd>
          </div>
          <div className="space-y-0.5">
            <dt className="text-xs text-muted-foreground">Dataset</dt>
            <dd className="text-sm font-medium text-foreground">
              {sensorHealth.datasetName}
            </dd>
          </div>
          <div className="space-y-0.5">
            <dt className="text-xs text-muted-foreground">Analysed period</dt>
            <dd className="text-sm font-medium text-foreground">
              {sensorHealth.periodStart} to {sensorHealth.periodEnd}
            </dd>
          </div>
          <div className="space-y-0.5">
            <dt className="text-xs text-muted-foreground">Mode</dt>
            <dd className="text-sm font-medium text-foreground">
              Historical analysis
            </dd>
          </div>
        </dl>
      </SectionCard>

      <section className="space-y-3">
        <h2 className="text-sm font-medium text-muted-foreground">Summary</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
          {sensorHealth.summaryKpis.map((kpi) => (
            <KpiCard
              key={kpi.label}
              title={kpi.label}
              value={kpi.value}
              description={kpi.description}
            />
          ))}
        </div>
      </section>

      <ChartContainer
        title="Sensor health distribution"
        description="Distribution of analysed signals by reliability status."
        footer="Critical or warning signals should be reviewed before using them for automated operational decisions."
      >
        <SensorHealthDistributionChart data={sensorHealth.distribution} />
      </ChartContainer>

      <SectionCard
        title="Problematic signals"
        description="Signals that may reduce trust in anomaly, drift or incident interpretation."
      >
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {sensorHealth.problematicSignals.map((signal) => (
            <div
              key={signal.sensorId}
              className="space-y-3 rounded-lg border p-4"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-0.5">
                  <p className="text-sm font-medium text-foreground">
                    {signal.displayName}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {signal.sensorId}
                  </p>
                </div>
                <StatusBadge
                  status={toBadgeStatus(signal.status)}
                  size="md"
                  className="min-w-20 justify-center"
                />
              </div>
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                <span>Coverage: {signal.coveragePct.toFixed(1)}%</span>
                <span>
                  Issues: {signal.issueTypes.map(humanizeIssueType).join(", ")}
                </span>
              </div>
              <p className="text-sm text-muted-foreground">
                {signal.recommendation}
              </p>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard
        title="Operational interpretation"
        description="How sensor reliability affects the intelligence layer."
      >
        <div className="space-y-3">
          {sensorHealth.insights.map((insight) => (
            <div
              key={insight.title}
              className="space-y-1 rounded-lg border p-4"
            >
              <p className="text-sm font-medium text-foreground">
                {insight.title}
              </p>
              <p className="text-sm text-muted-foreground">{insight.body}</p>
            </div>
          ))}
        </div>
      </SectionCard>
    </div>
  );
}
