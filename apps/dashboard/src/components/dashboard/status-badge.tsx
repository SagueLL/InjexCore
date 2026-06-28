import { Badge } from "@/components/ui/badge";

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

interface StatusBadgeProps {
  status: DashboardStatus;
  className?: string;
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const { label, variant } = STATUS_CONFIG[status];

  return (
    <Badge variant={variant} className={className}>
      {label}
    </Badge>
  );
}
