import { Bell } from "lucide-react";
import { org } from "@/lib/mock-data";
import { Badge } from "@/components/ui/badge";

export function TopBar({ title }: { title?: string }) {
  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-surface-border px-8">
      <div className="flex items-center gap-3">
        {title && (
          <p className="text-sm text-zinc-500 lg:hidden">{title}</p>
        )}
        <Badge variant="live" dot>
          {org.botsActive} bots live
        </Badge>
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          className="rounded-lg p-2 text-zinc-600 transition-colors hover:bg-white/[0.04] hover:text-zinc-400"
          aria-label="Notifications"
        >
          <Bell className="h-4 w-4" strokeWidth={1.75} />
        </button>
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-white/[0.06] text-xs font-medium text-zinc-400">
          AC
        </div>
      </div>
    </header>
  );
}
