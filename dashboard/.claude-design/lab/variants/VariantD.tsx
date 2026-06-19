import { PhoneCall } from "lucide-react";
import { OverviewPanel } from "../components/OverviewPanel";
import { liveCalls, navSections, org, stats } from "../data/fixtures";

/** D — Context panel: main content + right rail for live status */
export function VariantD() {
  return (
    <div className="flex h-[640px] overflow-hidden rounded-xl border border-surface-border bg-surface">
      <aside className="hidden w-48 shrink-0 flex-col border-r border-surface-border bg-surface-raised sm:flex">
        <div className="flex h-14 items-center gap-2 px-4">
          <PhoneCall className="h-4 w-4 text-brand" />
          <span className="text-body font-semibold">AI Fronter</span>
        </div>
        <nav className="flex-1 p-2">
          {navSections[0].items.map((item) => (
            <div key={item} className={`rounded-md px-3 py-2 text-body ${item === "Overview" ? "bg-surface-overlay font-medium" : "text-foreground-muted"}`}>
              {item}
            </div>
          ))}
        </nav>
      </aside>
      <main className="min-w-0 flex-1 overflow-y-auto">
        <OverviewPanel />
      </main>
      <aside className="hidden w-52 shrink-0 border-l border-surface-border bg-surface-raised p-4 lg:block">
        <p className="data-label">Live now</p>
        <p className="mt-1 text-2xl font-semibold tabular-nums">{liveCalls.length}</p>
        <p className="text-caption text-foreground-muted">agents on calls</p>
        <div className="mt-4 space-y-2">
          {liveCalls.map((c) => (
            <div key={c.bot} className="rounded-md border border-surface-border-subtle p-2">
              <p className="text-caption font-medium">{c.bot}</p>
              <p className="text-2xs text-foreground-faint">{c.status}</p>
            </div>
          ))}
        </div>
        <div className="mt-6 border-t border-surface-border-subtle pt-4">
          <p className="text-caption text-foreground-faint">Transfer rate</p>
          <p className="text-xl font-semibold tabular-nums">{stats.transferRate}%</p>
        </div>
      </aside>
    </div>
  );
}
