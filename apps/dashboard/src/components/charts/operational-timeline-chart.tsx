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

import type { TimelinePoint } from "@/types/timeline";

interface OperationalTimelineChartProps {
  data: TimelinePoint[];
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
  deviation: "var(--injex-green)",
  incidents: "#003773",
}

export function OperationalTimelineChart({
  data,
}: OperationalTimelineChartProps) {
  return (
    <div className="h-[320px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={chartColors.grid} vertical={false} />
          <XAxis dataKey="date" stroke="var(--muted-foreground)" tick={{ fontSize: 12 }} />
          <YAxis
            yAxisId="deviation"
            domain={[0, 1]}
            tickFormatter={(value) => Number(value).toFixed(1)}
            stroke="var(--muted-foreground)"
            tick={{ fontSize: 12 }}
          />
          <YAxis
            yAxisId="incidents"
            orientation="right"
            allowDecimals={false}
            stroke="var(--muted-foreground)"
            tick={{ fontSize: 12 }}
          />
          <Tooltip />
          <Legend/>
          <Bar
            yAxisId="incidents"
            dataKey="incidentCount"
            name="Incident windows"
            fill={chartColors.incidents}
            fillOpacity={0.5}
            radius={[6, 6, 0, 0]}
          />
          <Line
            yAxisId="deviation"
            type="monotone"
            dataKey="deviationScore"
            name="Deviation score"
            stroke={chartColors.deviation}
            strokeWidth={2}
            dot={{ r: 3 }}
            activeDot={{ r: 5 }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
