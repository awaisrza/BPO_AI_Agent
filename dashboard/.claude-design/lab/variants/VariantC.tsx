import { OverviewPanel } from "../components/OverviewPanel";
import { navSections, org } from "../data/fixtures";

/** C — Top nav: horizontal tabs, no sidebar — mobile-friendly pattern */
export function VariantC() {
  const tabs = navSections.flatMap((s) => s.items);

  return (
    <div className="flex h-[640px] flex-col overflow-hidden rounded-xl border border-surface-border bg-surface">
      <header className="border-b border-surface-border bg-surface-raised">
        <div className="flex h-14 items-center justify-between px-5">
          <p className="text-body font-semibold">AI Fronter</p>
          <span className="text-caption text-foreground-muted">{org.name}</span>
        </div>
        <div className="flex gap-1 overflow-x-auto px-5 pb-0">
          {tabs.map((tab) => (
            <div
              key={tab}
              className={`shrink-0 border-b-2 px-3 py-2 text-caption font-medium ${tab === "Overview" ? "border-brand text-foreground" : "border-transparent text-foreground-muted"}`}
            >
              {tab}
            </div>
          ))}
        </div>
      </header>
      <main className="flex-1 overflow-y-auto">
        <OverviewPanel />
      </main>
    </div>
  );
}
