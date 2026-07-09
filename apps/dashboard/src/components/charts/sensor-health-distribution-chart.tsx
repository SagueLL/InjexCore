"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Cell,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { SensorHealthDistributionItem } from "@/types/sensor-health";

interface SensorHealthDistributionChartProps {
  data: SensorHealthDistributionItem[];
}

type BarShapeProps = {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  payload?: SensorHealthDistributionItem;
};

const statusColors: Record<SensorHealthDistributionItem["status"], string> = {
  healthy: "var(--injex-green)",
  warning: "#f6bc00",
  critical: "#f62026",
  unknown: "#3c3c3c",
}

function SensorHealthBarShape({
  x = 0,
  y = 0,
  width = 0,
  height = 0,
  payload,
}: BarShapeProps) {
  const fill = payload ? statusColors[payload.status] : "#64748b";

  return (
    <rect
      x={x}
      y={y}
      width={width}
      height={height}
      rx={6}
      ry={6}
      fill={fill}
    />
  );
}

export function SensorHealthDistributionChart({
  data,
}: SensorHealthDistributionChartProps) {
  if (data.length === 0) {
    return (
      <div className="flex h-[320px] min-h-[320px] w-full min-w-0 items-center justify-center">
        <p className="text-sm text-muted-foreground">
          No sensor health data available.
        </p>
      </div>
    );
  }

  return (
    <div className="h-[320px] min-h-[320px] w-full min-w-0">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
          <XAxis dataKey="label" stroke="var(--muted-foreground)" tick={{ fontSize: 12 }} />
          <YAxis
            allowDecimals={false}
            stroke="var(--muted-foreground)"
            tick={{ fontSize: 12 }}
          />
          <Tooltip cursor={{ fill: "rgba(17, 22, 32, 0.04)" }} />
          <Bar
            dataKey="count"
            name="Signals"
            radius={[4, 4, 0, 0]}
            shape={(props) => <SensorHealthBarShape {...props} />}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
