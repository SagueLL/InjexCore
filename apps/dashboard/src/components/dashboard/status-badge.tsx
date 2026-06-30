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

export function StatusBadge({
  status,
  size = "sm",
  className,
}: StatusBadgeProps) {
  const { label, variant } = STATUS_CONFIG[status];

  return (
    <Badge variant={variant} className={cn(SIZE_CLASSES[size], className)}>
      {label}
    </Badge>
  );
}
