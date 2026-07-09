import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

interface KpiCardProps {
  title: string;
  value: string | number;
  description?: string;
  helperText?: string;
  className?: string;
}

// The API serves raw numbers, never preformatted strings. The locale is pinned:
// a floating locale would make the server and client render different digits and
// trip a hydration mismatch.
const NUMBER_FORMAT = new Intl.NumberFormat("en-US");

function formatValue(value: string | number): string {
  return typeof value === "number" ? NUMBER_FORMAT.format(value) : value;
}

export function KpiCard({
  title,
  value,
  description,
  helperText,
  className,
}: KpiCardProps) {
  return (
    <Card className="overflow-hidden border-border/80 bg-card shadow-sm transition-shadow hover:shadow-lg">
      <CardHeader>
        <CardTitle className="text-xs font-medium text-muted-foreground">
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-1">
        <div className="text-2xl font-semibold tracking-tight text-foreground">
          {formatValue(value)}
        </div>
        {description ? (
          <p className="text-xs text-muted-foreground">{description}</p>
        ) : null}
      </CardContent>
      {helperText ? (
        <CardFooter className="border-t text-xs text-muted-foreground">
          {helperText}
        </CardFooter>
      ) : null}
    </Card>
  );
}
