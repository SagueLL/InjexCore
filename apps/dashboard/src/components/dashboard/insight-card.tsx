import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

interface InsightCardProps {
  title: string;
  body: string;
  footer?: string;
  className?: string;
}

export function InsightCard({ title, body, footer, className }: InsightCardProps) {
  return (
    <Card className="overflow-hidden border-border/80 bg-card shadow-sm transition-shadow hover:shadow-lg">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">{body}</p>
      </CardContent>
      {footer ? (
        <CardFooter className="border-t text-xs text-muted-foreground">
          {footer}
        </CardFooter>
      ) : null}
    </Card>
  );
}
