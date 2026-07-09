interface PageHeaderProps {
  title: string;
  description?: string;
}

export function PageHeader({ title, description }: PageHeaderProps) {
  return (
    <header className="border-b border-border/70 pb-6">
      <div className="mb-4 h-1 w-16 rounded-full bg-[var(--injex-green)]" />

        <h1 className="text-3xl font-semibold tracking-tight text-foreground">
          {title}
        </h1>

        {description ? (
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">{description}</p>
        ) : null}
    </header>
  );
}
