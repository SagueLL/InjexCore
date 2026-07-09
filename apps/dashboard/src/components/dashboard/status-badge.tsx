import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

import type { OperationalStatus } from "@/types/dashboard";

export type DashboardStatus = OperationalStatus;

const STATUS_CONFIG: Record<
  DashboardStatus,
  { label: string; variant: React.ComponentProps<typeof Badge>["variant"] }
> = {
  normal: { label: "Normal", variant: "secondary" },
  warning: { label: "Warning", variant: "default" },
  critical: { label: "Critical", variant: "destructive" },
  unknown: { label: "Unknown", variant: "outline" },
};

const SIZE_CLASSES: Record<"sm" | "md", string> = {
  sm: "",
  md: "h-6 px-3 py-1 text-xs",
};

interface StatusBadgeProps {
  status: DashboardStatus;
  size?: "sm" | "md";
  className?: string;
}

const statusStyles = {
  normal:
    "border-green-200 bg-green-50 text-green-700",
  warning:
    "border-amber-200 bg-amber-50 text-amber-700",
  critical:
    "border-red-200 bg-red-50 text-red-700",
  unknown:
    "border-slate-200 bg-slate-50 text-slate-600",
}

export function StatusBadge({
  status,
  size = "sm",
  className,
}: StatusBadgeProps) {
  const { label, variant } = STATUS_CONFIG[status];

  return (
    <Badge variant={variant} className={cn(SIZE_CLASSES[size], className, statusStyles[status])}>
      {label}
    </Badge>
  );
}
