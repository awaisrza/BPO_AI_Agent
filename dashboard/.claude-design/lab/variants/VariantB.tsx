import { PhoneCall } from "lucide-react";
import { OverviewPanel } from "../components/OverviewPanel";
import { navSections, org } from "../data/fixtures";

const allNav = navSections.flatMap((s) => s.items);

/** B — Icon rail: compact sidebar, maximum content width */
export function VariantB() {
  return (
    <div className="flex h-[640px] overflow-hidden rounded-xl border border-surface-border bg-surface">
      <aside className="flex w-14 shrink-0 flex-col items-center border-r border-surface-border bg-surface py-4">
        <div className="mb-6 flex h-9 w-9 items-center justify-center rounded-md bg-brand-muted">
          <PhoneCall className="h-4 w-4 text-brand" />
        </div>
        {allNav.slice(0, 6).map((item, i) => (
          <div
            key={item}
            className={`mb-1 flex h-9 w-9 items-center justify-center rounded-md text-2xs ${i === 0 ? "bg-brand-muted text-brand" : "text-foreground-faint"}`}
            title={item}
          >
            {item[0]}
          </div>
        ))}
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 items-center justify-between border-b border-surface-border px-5">
          <div>
            <p className="text-caption text-foreground-faint">{org.name}</p>
            <p className="text-body font-medium">Overview</p>
          </div>
        </header>
        <main className="flex-1 overflow-y-auto">
          <OverviewPanel />
        </main>
      </div>
    </div>
  );
}
