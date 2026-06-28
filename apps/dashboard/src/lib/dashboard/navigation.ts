import type { IconSvgElement } from "@hugeicons/react";
import {
  Activity03Icon,
  Alert02Icon,
  ChartLineData02Icon,
  Clock01Icon,
  DashboardSquare01Icon,
} from "@hugeicons/core-free-icons";

export interface NavItem {
  title: string;
  href: string;
  icon: IconSvgElement;
}

export const dashboardNav: NavItem[] = [
  { title: "Overview", href: "/overview", icon: DashboardSquare01Icon },
  { title: "Timeline", href: "/timeline", icon: Clock01Icon },
  { title: "Sensor Health", href: "/sensor-health", icon: Activity03Icon },
  { title: "Drift & Anomaly", href: "/drift-anomaly", icon: ChartLineData02Icon },
  { title: "Incidents", href: "/incidents", icon: Alert02Icon },
];
