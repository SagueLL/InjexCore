import Link from "next/link";

import { SidebarNav } from "@/components/app/sidebar-nav";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen w-full bg-background text-foreground">
      <aside className="flex w-64 shrink-0 flex-col border-r border-sidebar-border bg-sidebar">
        <div className="flex h-16 items-center border-b border-sidebar-border px-5">
          <Link href="/overview" className="flex flex-col leading-tight">
            <span className="text-sm font-semibold text-sidebar-foreground">
              InjexCore
            </span>
            <span className="text-xs text-muted-foreground">
              Industrial Intelligence
            </span>
          </Link>
        </div>
        <SidebarNav />
      </aside>
      <main className="flex-1 overflow-x-hidden">
        <div className="mx-auto max-w-7xl px-6 py-8 lg:px-8">{children}</div>
      </main>
    </div>
  );
}
