"use client";

import { useMemo, useState } from "react";
import { BarChart3, Download, PieChart } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConversionPieChart } from "@/components/analytics/conversion-pie-chart";
import { funnel, stats } from "@/lib/mock-data";
import { cn } from "@/lib/utils";

type Section = "overview" | "conversion";

const SECTIONS: {
  id: Section;
  label: string;
  hint: string;
  icon: typeof BarChart3;
  dot: string;
}[] = [
  {
    id: "overview",
    label: "Overview",
    hint: "Rates · ops metrics",
    icon: BarChart3,
    dot: "bg-brand",
  },
  {
    id: "conversion",
    label: "Conversion",
    hint: "Dials to transfer",
    icon: PieChart,
    dot: "bg-status-info",
  },
];

const PIE_COLORS = [
  "var(--brand)",
  "var(--status-info)",
  "var(--status-success)",
  "var(--status-warning)",
];

export function AnalyticsPageClient() {
  const [section, setSection] = useState<Section>("conversion");
  const active = useMemo(() => SECTIONS.find((s) => s.id === section)!, [section]);

  const slices = useMemo(
    () =>
      funnel.map((step, i) => ({
        label: step.label,
        value: step.value,
        color: PIE_COLORS[i % PIE_COLORS.length],
      })),
    [],
  );

  return (
    <div className="analytics-shell relative flex h-full min-h-0 flex-1 flex-col overflow-hidden bg-surface-raised">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_80%_50%_at_0%_0%,rgba(59,130,246,0.12),transparent_55%),radial-gradient(ellipse_60%_40%_at_100%_100%,rgba(15,23,42,0.85),transparent_55%)]"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.28] [background-image:linear-gradient(rgba(255,255,255,0.028)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.028)_1px,transparent_1px)] [background-size:40px_40px] [mask-image:radial-gradient(ellipse_at_center,black_40%,transparent_85%)]"
      />

      <div className="relative flex min-h-0 flex-1 flex-col lg:flex-row">
        <aside className="flex w-full shrink-0 flex-col border-b border-surface-border-subtle bg-surface/75 backdrop-blur-md lg:h-full lg:w-56 lg:border-b-0 lg:border-r">
          <div className="border-b border-surface-border-subtle px-4 py-4">
            <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-foreground-faint">
              Reporting
            </p>
            <h1 className="mt-1 text-lg font-semibold tracking-tight text-foreground">
              Analytics
            </h1>
            <p className="mt-1 text-caption text-foreground-muted">14-day window</p>
          </div>

          <nav className="flex gap-1 overflow-x-auto p-2 scrollbar-thin lg:min-h-0 lg:flex-1 lg:flex-col lg:overflow-y-auto">
            {SECTIONS.map((item) => {
              const Icon = item.icon;
              const selected = section === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setSection(item.id)}
                  className={cn(
                    "flex shrink-0 items-center gap-2 rounded-md px-3 py-2.5 text-left transition-colors duration-150 lg:w-full",
                    selected
                      ? "bg-surface-overlay text-foreground shadow-[inset_2px_0_0_0_var(--brand)]"
                      : "text-foreground-muted hover:bg-surface-overlay/60 hover:text-foreground-secondary",
                  )}
                >
                  <span className={cn("h-2 w-2 shrink-0 rounded-full", item.dot)} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-caption font-medium">{item.label}</span>
                    <span className="mt-0.5 hidden truncate text-2xs text-foreground-faint lg:block">
                      {item.hint}
                    </span>
                  </span>
                  <Icon className="hidden h-3.5 w-3.5 shrink-0 text-foreground-faint lg:block" />
                </button>
              );
            })}
          </nav>
        </aside>

        <section className="flex min-h-0 min-w-0 flex-1 flex-col">
          <header className="flex flex-col gap-3 border-b border-surface-border-subtle bg-surface-raised/80 px-4 py-3 backdrop-blur-md sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <p className="text-2xs font-semibold uppercase tracking-[0.12em] text-foreground-faint">
                {active.hint}
              </p>
              <h2 className="mt-0.5 text-base font-semibold tracking-tight text-foreground">
                {active.label}
              </h2>
            </div>
            <Button variant="secondary" size="sm">
              <Download className="h-3.5 w-3.5" />
              Export
            </Button>
          </header>

          <div className="min-h-0 flex-1 overflow-y-auto scrollbar-thin">
            <div className="mx-auto flex w-full max-w-5xl flex-col justify-center px-5 py-8 sm:px-8 lg:min-h-full lg:px-10">
              {section === "overview" && (
                <div className="mx-auto w-full max-w-4xl space-y-6">
                  <div className="grid gap-4 sm:grid-cols-3">
                    <MetricTile
                      label="Connect rate"
                      value={`${stats.connectRate}%`}
                      accent="text-status-success"
                    />
                    <MetricTile
                      label="Transfer rate"
                      value={`${stats.transferRate}%`}
                      accent="text-brand"
                    />
                    <MetricTile
                      label="Avg duration"
                      value={`${stats.avgDurationSec}s`}
                      accent="text-foreground"
                    />
                  </div>

                  <div className="rounded-md border border-surface-border-subtle bg-surface-overlay/40 p-5 sm:p-6">
                    <p className="mb-5 text-2xs font-semibold uppercase tracking-[0.12em] text-foreground-faint">
                      Operational metrics
                    </p>
                    <div className="grid gap-4 sm:grid-cols-3">
                      <MetricTile
                        label="Avg active min / agent"
                        value={stats.activeMinPerBot.toLocaleString()}
                        compact
                      />
                      <MetricTile label="AMD drop rate" value="94%" compact />
                      <MetricTile label="Reporting period" value="14 days" compact />
                    </div>
                  </div>
                </div>
              )}

              {section === "conversion" && (
                <div className="mx-auto w-full max-w-4xl rounded-md border border-surface-border-subtle bg-surface-overlay/40 px-6 py-10 sm:px-10 sm:py-12">
                  <p className="mb-8 text-center text-body text-foreground-muted">
                    Share of each stage from dials to qualified transfer
                  </p>
                  <ConversionPieChart slices={slices} title="Stages" />
                </div>
              )}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function MetricTile({
  label,
  value,
  accent,
  compact,
}: {
  label: string;
  value: string;
  accent?: string;
  compact?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-md border border-surface-border-subtle bg-surface-overlay/55",
        compact ? "px-4 py-4" : "px-5 py-5",
      )}
    >
      <p className="text-2xs uppercase tracking-wide text-foreground-faint">{label}</p>
      <p
        className={cn(
          "mt-1.5 font-semibold tabular-nums tracking-tight",
          compact ? "text-xl text-foreground" : "text-3xl",
          accent ?? "text-foreground",
        )}
      >
        {value}
      </p>
    </div>
  );
}
