import Link from "next/link";

import { SidebarNav } from "@/components/app/sidebar-nav";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen w-full bg-background text-foreground">
      <aside className="sticky top-0 flex h-screen w-60 shrink-0 flex-col border-r border-sidebar-border bg-[var(--injex-navy)]">
        <div className="flex h-20 items-center border-b border-sidebar-border px-5">
          <Link href="/overview" className="grid w-full grid-cols-[1fr_auto] items-center gap-4">

            <div className="min-w-0">
              <p className="text-sm font-semibold tracking-wide text-white">
                InjexCore
              </p>
              <p className="mt-1 whitespace-nowrap text-xs text-white/55">
                Industrial Intelligence
              </p>
            </div>

            <img
              src="/brand/ICONO_MARCO.png"
              alt="Injex Logo"
              className="h-9 w-9 shrink-0"
            />

          </Link>
        </div>

        <SidebarNav />
          <div className="mt-auto border-t border-white/10 px-5 py-4">
            <p className="text-xs leading-5 text-white/45">
            Dashboard v0.1
              <br />
              Historical analysis
            </p>
          </div>
        </aside>

      <main className="min-w-0 flex-1 overflow-x-hidden">
        <div className="mx-auto max-w-7xl px-6 py-8 lg:px-8">{children}</div>
      </main>
    </div>
  );
}
