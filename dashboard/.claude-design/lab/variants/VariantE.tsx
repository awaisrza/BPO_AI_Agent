import { PhoneCall } from "lucide-react";
import { OverviewPanel } from "../components/OverviewPanel";
import { navSections, org } from "../data/fixtures";

/** E — Premium spacious: wider gutters, softer surfaces, larger type scale */
export function VariantE() {
  return (
    <div className="flex h-[640px] overflow-hidden rounded-xl border border-surface-border-subtle bg-[#0c0c0e] shadow-sm">
      <aside className="flex w-64 shrink-0 flex-col bg-[#0a0a0c] px-4 py-6">
        <div className="mb-8 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand/20">
            <PhoneCall className="h-5 w-5 text-brand" />
          </div>
          <div>
            <p className="text-body font-semibold tracking-tight">AI Fronter</p>
            <p className="text-caption text-foreground-faint">Premium workspace</p>
          </div>
        </div>
        {navSections.map((section) => (
          <div key={section.title} className="mb-6">
            <p className="mb-2 text-2xs font-medium uppercase tracking-widest text-foreground-faint">{section.title}</p>
            <div className="space-y-1">
              {section.items.map((item) => (
                <div
                  key={item}
                  className={`rounded-lg px-3 py-2.5 text-body transition-colors ${item === "Overview" ? "bg-white/5 font-medium text-foreground" : "text-foreground-muted"}`}
                >
                  {item}
                </div>
              ))}
            </div>
          </div>
        ))}
        <div className="mt-auto rounded-lg bg-white/[0.03] p-3">
          <p className="text-body font-medium">{org.name}</p>
          <p className="text-caption text-foreground-faint">{org.plan} plan</p>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 items-center px-8">
          <h1 className="text-lg font-semibold tracking-tight">Overview</h1>
        </header>
        <main className="flex-1 overflow-y-auto px-2">
          <div className="rounded-xl bg-surface-raised/50">
            <OverviewPanel />
          </div>
        </main>
      </div>
    </div>
  );
}
