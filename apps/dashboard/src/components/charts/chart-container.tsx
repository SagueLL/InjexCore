import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

interface ChartContainerProps {
  title: string;
  description?: string;
  children: React.ReactNode;
  footer?: string;
  className?: string;
}

export function ChartContainer({
  title,
  description,
  children,
  footer,
  className,
}: ChartContainerProps) {
  return (
    <Card className="overflow-hidden border-border/80 bg-card shadow-sm">
      <CardHeader>
        <CardTitle className="text-base font-semibold">{title}</CardTitle>
        {description ? <CardDescription className="text-sm leading-6 text-muted-foreground">{description}</CardDescription> : null}
      </CardHeader>
      <CardContent>
        {children}
      </CardContent>
      {footer ? (
        <CardFooter className="border-t text-xs text-muted-foreground">
          {footer}
        </CardFooter>
      ) : null}
    </Card>
  );
}
