import { PageHeader } from "@/components/app/page-header";
import { ChartContainer } from "@/components/charts/chart-container";
import { OperationalTimelineChart } from "@/components/charts/operational-timeline-chart";
import { KpiCard } from "@/components/dashboard/kpi-card";
import { NoticeStrip } from "@/components/dashboard/notice-strip";
import { SectionCard } from "@/components/dashboard/section-card";
import { StatusBadge } from "@/components/dashboard/status-badge";
import { getTimelinePayload } from "@/lib/dashboard/data-access";

import type { OperationalStatus } from "@/types/dashboard";
import type { TimelineStatus } from "@/types/timeline";

// StatusBadge has no dedicated "drift" variant yet; surface drift as a warning
// for now (the period title still carries the drift meaning). Note that on the
// pinned run the API never emits "drift": every day overlapping an active or
// persistent drift event is also overlapped by an anomaly/critical incident, and
// critical outranks drift in the ladder.
function toBadgeStatus(status: TimelineStatus): OperationalStatus {
  return status === "drift" ? "warning" : status;
}

export default async function TimelinePage() {
  const { meta, data: timeline } = await getTimelinePayload();

  return (
    <div className="space-y-6">
      <PageHeader
        title="Operational Timeline"
        description="Temporal view of operational behaviour, drift and incident concentration."
      />

      <NoticeStrip notices={meta.notices} />

      <SectionCard title="Analysed context">
        <dl className="grid grid-cols-1 gap-x-8 gap-y-2 sm:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-0.5">
            <dt className="text-xs text-muted-foreground">Asset</dt>
            <dd className="text-sm font-medium text-foreground">
              {timeline.assetName}
            </dd>
          </div>
          <div className="space-y-0.5">
            <dt className="text-xs text-muted-foreground">Dataset</dt>
            <dd className="text-sm font-medium text-foreground">
              {timeline.datasetName}
            </dd>
          </div>
          <div className="space-y-0.5">
            <dt className="text-xs text-muted-foreground">Analysed period</dt>
            <dd className="text-sm font-medium text-foreground">
              {timeline.periodStart} to {timeline.periodEnd}
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
          {timeline.summaryKpis.map((kpi) => (
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
        title="Operational behaviour over time"
        description="Share of production rows carrying anomaly evidence, and incident concentration, across the analysed period."
        footer="Evidence share is the fraction of a day's scored rows flagged warning or anomaly — a rate, not a model score. A day is marked warning at 5% or more. Recurring-pattern incidents spanning most of the period are excluded from the daily series; they remain in the incident total and in the Incidents view."
      >
        <OperationalTimelineChart data={timeline.series} />
      </ChartContainer>

      <SectionCard
        title="Interpretive periods"
        description="How operational behaviour evolved across the analysed window."
      >
        <div className="space-y-3">
          {timeline.periods.map((period) => (
            <div
              key={period.title}
              className="flex items-center justify-between gap-4 rounded-lg border p-4"
            >
              <div className="space-y-1">
                <span className="text-sm font-medium text-foreground">
                  {period.title}
                </span>
                <p className="text-xs text-muted-foreground">
                  {period.startDate} to {period.endDate}
                </p>
                <p className="text-sm text-muted-foreground">
                  {period.description}
                </p>
              </div>
              <StatusBadge
                status={toBadgeStatus(period.status)}
                size="md"
                className="min-w-20 justify-center"
              />
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard
        title="Timeline events"
        description="Notable operational events across the analysed period."
      >
        <ul className="space-y-3">
          {timeline.events.map((event) => (
            <li
              key={event.title}
              className="flex items-center justify-between gap-4 border-b pb-3 last:border-b-0 last:pb-0"
            >
              <div className="space-y-1">
                <span className="text-sm font-medium text-foreground">
                  {event.title}
                </span>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span>{event.date}</span>
                  <span>·</span>
                  <span className="capitalize">{event.type}</span>
                </div>
                <p className="text-sm text-muted-foreground">
                  {event.description}
                </p>
              </div>
              <StatusBadge
                status={event.severity}
                size="md"
                className="min-w-20 justify-center"
              />
            </li>
          ))}
        </ul>
      </SectionCard>
    </div>
  );
}
