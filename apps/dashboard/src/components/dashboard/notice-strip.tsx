import { cn } from "@/lib/utils";

import type { DashboardNotice } from "@/types/dashboard-api";

interface NoticeStripProps {
  notices: DashboardNotice[];
  className?: string;
}

// The notices are contract copy, served verbatim by the API (data contract §5.4).
// They are never rewritten, summarised or filtered here — the frontend only decides
// where they appear, not what they say.
export function NoticeStrip({ notices, className }: NoticeStripProps) {
  if (notices.length === 0) {
    return null;
  }

  return (
    <aside
      aria-label="Interpretation notices"
      className={cn(
        "rounded-lg border border-amber-200/80 bg-amber-50/60 px-4 py-3",
        className,
      )}
    >
      <ul className="space-y-1.5">
        {notices.map((notice) => (
          <li
            key={notice.key}
            className="flex gap-2.5 text-xs leading-5 text-amber-900"
          >
            <span aria-hidden className="select-none text-amber-500">
              &bull;
            </span>
            <span>{notice.text}</span>
          </li>
        ))}
      </ul>
    </aside>
  );
}
