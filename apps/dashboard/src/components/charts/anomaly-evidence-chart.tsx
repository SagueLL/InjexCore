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
            yAxisId="score"
            domain={[0, 1]}
            tickFormatter={(value) => Number(value).toFixed(1)}
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
          <Tooltip />
          <Legend />
          <Bar
            yAxisId="counts"
            dataKey="anomalyCount"
            name="Anomaly windows"
            fill="var(--muted-foreground)"
            fillOpacity={0.3}
            radius={[2, 2, 0, 0]}
          />
          <Bar
            yAxisId="counts"
            dataKey="residualCount"
            name="Residual review"
            fill="var(--primary)"
            fillOpacity={0.35}
            radius={[2, 2, 0, 0]}
          />
          <Line
            yAxisId="score"
            type="monotone"
            dataKey="anomalyScore"
            name="Anomaly score"
            stroke="var(--primary)"
            strokeWidth={2}
            dot={{ r: 3 }}
            activeDot={{ r: 5 }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
