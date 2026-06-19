import { PhoneCall } from "lucide-react";
import { OverviewPanel } from "../components/OverviewPanel";
import { navSections, org } from "../data/fixtures";

/** A — Stripe-refined sidebar: elevated nav surface, subtle section dividers */
export function VariantA() {
  return (
    <div className="flex h-[640px] overflow-hidden rounded-xl border border-surface-border bg-surface">
      <aside className="flex w-56 shrink-0 flex-col border-r border-surface-border bg-surface-raised">
        <div className="flex h-14 items-center gap-2 border-b border-surface-border-subtle px-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand text-brand-foreground">
            <PhoneCall className="h-4 w-4" />
          </div>
          <div>
            <p className="text-body font-semibold">AI Fronter</p>
            <p className="text-2xs text-foreground-faint">Call center platform</p>
          </div>
        </div>
        <nav className="flex-1 overflow-y-auto p-3">
          {navSections.map((section) => (
            <div key={section.title} className="mb-4">
              <p className="mb-1 px-2 text-2xs font-medium uppercase tracking-wider text-foreground-faint">{section.title}</p>
              {section.items.map((item, i) => (
                <div
                  key={item}
                  className={`rounded-md px-2 py-1.5 text-body ${item === "Overview" ? "bg-brand-muted font-medium text-foreground" : "text-foreground-muted"}`}
                >
                  {item}
                </div>
              ))}
            </div>
          ))}
        </nav>
        <div className="border-t border-surface-border-subtle p-3 text-caption text-foreground-faint">
          {org.name} · {org.plan}
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center justify-between border-b border-surface-border-subtle px-6">
          <span className="text-body font-medium">Overview</span>
          <div className="h-8 w-8 rounded-full bg-surface-overlay" />
        </header>
        <main className="flex-1 overflow-y-auto bg-surface">
          <OverviewPanel />
        </main>
      </div>
    </div>
  );
}
