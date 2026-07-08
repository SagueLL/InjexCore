import { Skeleton } from "@/components/ui/skeleton";

// Server Component: no interactivity, just the page shell every view shares
// (header, notice strip, context row, KPI row, chart, sections). The first hit
// after an API restart pays for the pinned run's parquet reads.
export default function Loading() {
  return (
    <div className="space-y-6" aria-busy aria-label="Loading dashboard data">
      <header className="border-b border-border/70 pb-6">
        <div className="mb-4 h-1 w-16 rounded-full bg-[var(--injex-green)]" />
        <Skeleton className="h-9 w-80" />
        <Skeleton className="mt-3 h-4 w-[28rem]" />
      </header>

      <Skeleton className="h-16 w-full rounded-lg" />
      <Skeleton className="h-24 w-full rounded-lg" />

      <section className="space-y-3">
        <Skeleton className="h-4 w-28" />
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map((index) => (
            <Skeleton key={index} className="h-32 rounded-lg" />
          ))}
        </div>
      </section>

      <Skeleton className="h-[26rem] w-full rounded-lg" />
      <Skeleton className="h-56 w-full rounded-lg" />
    </div>
  );
}
