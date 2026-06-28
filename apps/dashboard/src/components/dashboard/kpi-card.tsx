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

export function KpiCard({
  title,
  value,
  description,
  helperText,
  className,
}: KpiCardProps) {
  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle className="text-xs font-medium text-muted-foreground">
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-1">
        <div className="text-2xl font-semibold tracking-tight text-foreground">
          {value}
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
