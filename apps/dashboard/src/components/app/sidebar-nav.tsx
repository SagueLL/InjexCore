"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { HugeiconsIcon } from "@hugeicons/react";

import { cn } from "@/lib/utils";
import { dashboardNav } from "@/lib/dashboard/navigation";

export function SidebarNav() {
  const pathname = usePathname();

  return (
    <nav className="flex flex-col gap-1 p-3">
      {dashboardNav.map((item) => {
        const isActive =
          pathname === item.href || pathname.startsWith(`${item.href}/`);

        return (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              isActive
                ? "bg-sidebar-accent text-sidebar-accent-foreground"
                : "text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground",
            )}
          >
            <HugeiconsIcon 
            icon={item.icon}
            size={18}
            strokeWidth={2}
            className={cn(
              "shrink-0 transition-colors",
              isActive
                ? "text-white" : "text-white/55 group-hover:text-white",
            )}
            />
            <span>{item.title}</span>
          </Link>
        );
      })}
    </nav>
  );
}
