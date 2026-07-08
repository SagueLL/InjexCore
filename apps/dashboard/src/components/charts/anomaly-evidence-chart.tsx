"use client";

import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { AnomalyEvidencePoint } from "@/types/drift-anomaly";

interface AnomalyEvidenceChartProps {
  data: AnomalyEvidencePoint[];
}

const chartColors = {
  green: "var(--injex-green)",
  greenBright: "var(--injex-green-bright)",
  steel: "var(--injex-steel)",
  navy: "var(--injex-navy)",
  warning: "#d97706",
  critical: "#dc2626",
  neutral: "#64748b",
  grid: "#e2e8f0",
  incidents: "#003773",
}

const PERCENT = new Intl.NumberFormat("en-US", {
  style: "percent",
  maximumFractionDigits: 1,
});

function formatEvidenceShare(value: number): string {
  return PERCENT.format(value);
}

export function AnomalyEvidenceChart({ data }: AnomalyEvidenceChartProps) {
  if (data.length === 0) {
    return (
      <div className="flex h-[340px] min-h-[340px] w-full min-w-0 items-center justify-center">
        <p className="text-sm text-muted-foreground">
          No anomaly evidence available.
        </p>
      </div>
    );
  }

  return (
    <div className="h-[340px] min-h-[340px] w-full min-w-0">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
          <XAxis dataKey="date" stroke="var(--muted-foreground)" tick={{ fontSize: 12 }} />
          <YAxis
            yAxisId="share"
            domain={[0, 1]}
            tickFormatter={formatEvidenceShare}
            stroke="var(--muted-foreground)"
            tick={{ fontSize: 12 }}
          />
          <YAxis
            yAxisId="counts"
            orientation="right"
            allowDecimals={false}
            stroke="var(--muted-foreground)"
            tick={{ fontSize: 12 }}
          />
          <Tooltip
            formatter={(value, name) =>
              name === "Non-normal evidence share"
                ? formatEvidenceShare(Number(value))
                : value
            }
          />
          <Legend />
          {/* anomalyCount is non-normal scored *rows* per day, not windows. */}
          <Bar
            yAxisId="counts"
            dataKey="anomalyCount"
            name="Anomaly rows"
            fill={chartColors.incidents}
            fillOpacity={0.4}
            radius={[2, 2, 0, 0]}
          />
          <Bar
            yAxisId="counts"
            dataKey="residualCount"
            name="Residual review rows"
            fill={chartColors.warning}
            fillOpacity={0.4}
            radius={[2, 2, 0, 0]}
          />
          <Line
            yAxisId="share"
            type="monotone"
            dataKey="evidenceShare"
            name="Non-normal evidence share"
            stroke={chartColors.green}
            strokeWidth={2}
            dot={{ r: 3 }}
            activeDot={{ r: 5 }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
