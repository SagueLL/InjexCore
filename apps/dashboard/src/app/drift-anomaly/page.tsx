import { PageHeader } from "@/components/app/page-header";
import { AnomalyEvidenceChart } from "@/components/charts/anomaly-evidence-chart";
import { ChartContainer } from "@/components/charts/chart-container";
import { KpiCard } from "@/components/dashboard/kpi-card";
import { SectionCard } from "@/components/dashboard/section-card";
import { StatusBadge } from "@/components/dashboard/status-badge";
import { demoDriftAnomalySummary } from "@/lib/dashboard/demo-drift-anomaly";

import type { ContributionLevel } from "@/types/drift-anomaly";

function formatContribution(contribution: ContributionLevel): string {
  return contribution.charAt(0).toUpperCase() + contribution.slice(1);
}

function formatCount(value: number): string {
  return value.toLocaleString("en-US");
}

export default function DriftAnomalyPage() {
  const driftAnomaly = demoDriftAnomalySummary;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Drift & Anomaly Intelligence"
        description="Behavioural deviation and anomaly evidence across the analysed period."
      />

      <SectionCard
        title="Analysed context"
        description="Current anomaly and drift scope for the historical dataset."
      >
        <dl className="grid grid-cols-1 gap-x-8 gap-y-2 sm:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-0.5">
            <dt className="text-xs text-muted-foreground">Asset</dt>
            <dd className="text-sm font-medium text-foreground">
              {driftAnomaly.assetName}
            </dd>
          </div>
          <div className="space-y-0.5">
            <dt className="text-xs text-muted-foreground">Dataset</dt>
            <dd className="text-sm font-medium text-foreground">
              {driftAnomaly.datasetName}
            </dd>
          </div>
          <div className="space-y-0.5">
            <dt className="text-xs text-muted-foreground">Analysed period</dt>
            <dd className="text-sm font-medium text-foreground">
              {driftAnomaly.periodStart} to {driftAnomaly.periodEnd}
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
          {driftAnomaly.summaryKpis.map((kpi) => (
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
        title="Anomaly evidence over time"
        description="Raw anomaly evidence, residual review volume and deviation score across the analysed period."
        footer="Residual review represents anomaly evidence that remains after contextual filtering and should be interpreted with operational knowledge."
      >
        <AnomalyEvidenceChart data={driftAnomaly.evidenceSeries} />
      </ChartContainer>

      <SectionCard
        title="Detection methods"
        description="Model and context layers contributing to the anomaly evidence."
      >
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {driftAnomaly.detectionMethods.map((method) => (
            <div key={method.method} className="space-y-2 rounded-lg border p-4">
              <p className="text-sm font-medium text-foreground">
                {method.label}
              </p>
              <p className="text-xs text-muted-foreground">
                Evidence windows: {formatCount(method.evidenceCount)}
              </p>
              <p className="text-sm text-muted-foreground">
                {method.description}
              </p>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard
        title="Top affected signals"
        description="Signals most involved in the remaining anomaly and drift evidence."
      >
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {driftAnomaly.affectedSignals.map((signal) => (
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
                  status={signal.severity}
                  size="md"
                  className="min-w-20 justify-center"
                />
              </div>
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                <span>
                  Contribution: {formatContribution(signal.contribution)}
                </span>
              </div>
              <p className="text-sm text-muted-foreground">
                {signal.interpretation}
              </p>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard
        title="Operational interpretation"
        description="How drift and anomaly evidence should be understood in the current v0."
      >
        <div className="space-y-3">
          {driftAnomaly.insights.map((insight) => (
            <div key={insight.title} className="space-y-1 rounded-lg border p-4">
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
