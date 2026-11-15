"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Activity,
  LayoutDashboard,
  Megaphone,
  Phone,
  RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useOrg } from "@/components/layout/org-provider";
import { ConversionPieChart } from "@/components/analytics/conversion-pie-chart";
import { campaigns as mockCampaigns, funnel, liveCalls, stats, transferTrend } from "@/lib/mock-data";
import { createClient, isSupabaseConfigured } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

type Section = "snapshot" | "live" | "campaigns";

const SECTIONS: {
  id: Section;
  label: string;
  hint: string;
  icon: typeof LayoutDashboard;
  dot: string;
}[] = [
  {
    id: "snapshot",
    label: "Snapshot",
    hint: "Today · rates",
    icon: LayoutDashboard,
    dot: "bg-brand",
  },
  {
    id: "live",
    label: "Live activity",
    hint: "Agents on calls",
    icon: Activity,
    dot: "bg-status-success",
  },
  {
    id: "campaigns",
    label: "Campaigns",
    hint: "Running · paused",
    icon: Megaphone,
    dot: "bg-status-info",
  },
];

const PIE_COLORS = [
  "var(--brand)",
  "var(--status-info)",
  "var(--status-success)",
  "var(--status-warning)",
];

const STATUS_DOT: Record<string, string> = {
  live: "bg-status-success",
  ringing: "bg-status-warning",
  dialing: "bg-status-info",
  idle: "bg-foreground-faint",
  offline: "bg-foreground-faint",
  running: "bg-status-success",
  paused: "bg-foreground-faint",
};

export function OverviewPageClient() {
  const org = useOrg();
  const [section, setSection] = useState<Section>("snapshot");
  const [syncing, setSyncing] = useState(false);
  const [agentCount, setAgentCount] = useState<number | null>(null);
  const [runningCount, setRunningCount] = useState<number | null>(null);
  const [campaignRows, setCampaignRows] = useState<
    { id: string; name: string; status: string; bots: number }[]
  >([]);
  const [hint, setHint] = useState("");

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

  const load = useCallback(async (opts?: { quiet?: boolean }) => {
    if (!isSupabaseConfigured()) {
      setCampaignRows(
        mockCampaigns.map((c) => ({
          id: c.id,
          name: c.name,
          status: c.status,
          bots: c.bots,
        })),
      );
      setAgentCount(org.botsActive);
      setRunningCount(mockCampaigns.filter((c) => c.status === "running").length);
      setHint("Showing sample metrics — connect Supabase for live counts.");
      return;
    }

    if (!opts?.quiet) setSyncing(true);
    try {
      const supabase = createClient();
      const [{ count: bots }, { data: camps }] = await Promise.all([
        supabase.from("bots").select("*", { count: "exact", head: true }),
        supabase.from("campaigns").select("id, name, status").order("name"),
      ]);

      const { data: botLinks } = await supabase.from("bots").select("campaign_id");
      const botCounts = (botLinks ?? []).reduce<Record<string, number>>((acc, row) => {
        if (row.campaign_id) {
          acc[row.campaign_id] = (acc[row.campaign_id] ?? 0) + 1;
        }
        return acc;
      }, {});

      const rows = (camps ?? []).map((c) => ({
        id: c.id as string,
        name: c.name as string,
        status: c.status as string,
        bots: botCounts[c.id as string] ?? 0,
      }));

      setAgentCount(bots ?? 0);
      setCampaignRows(rows);
      setRunningCount(rows.filter((c) => c.status === "running").length);
      setHint(`Synced — ${rows.length} campaign${rows.length === 1 ? "" : "s"}, ${bots ?? 0} agents`);
    } catch {
      setHint("Could not refresh live counts.");
    } finally {
      setSyncing(false);
    }
  }, [org.botsActive]);

  useEffect(() => {
    void load({ quiet: true });
  }, [load]);

  const maxTrend = Math.max(...transferTrend.map((d) => d.rate), 1);

  return (
    <div className="overview-shell relative flex h-full min-h-0 flex-1 flex-col overflow-hidden bg-surface-raised">
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
              Operations
            </p>
            <h1 className="mt-1 text-lg font-semibold tracking-tight text-foreground">Overview</h1>
            <p className="mt-1 truncate text-caption text-foreground-muted">{org.name}</p>
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

          <div className="mt-auto hidden space-y-2 border-t border-surface-border-subtle p-3 lg:block">
            <MiniStat
              label="Agents"
              value={agentCount ?? org.botsActive}
              accent="text-foreground"
            />
            <MiniStat
              label="Running"
              value={runningCount ?? 0}
              accent="text-status-success"
            />
          </div>
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
            <div className="flex shrink-0 items-center gap-2">
              <Button variant="secondary" size="sm" href="/calls">
                <Phone className="h-3.5 w-3.5" />
                Calls
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() => void load()}
                disabled={syncing}
              >
                <RefreshCw className={cn("h-3.5 w-3.5", syncing && "animate-spin")} />
                {syncing ? "Syncing…" : "Sync"}
              </Button>
            </div>
          </header>

          <div className="min-h-0 flex-1 overflow-y-auto scrollbar-thin">
            <div className="mx-auto w-full max-w-3xl space-y-5 px-5 py-6">
              {hint && (
                <p className="rounded-md border border-surface-border bg-surface-overlay/80 px-3 py-2 text-caption text-foreground-muted">
                  {hint}
                </p>
              )}

              {section === "snapshot" && (
                <>
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    <MetricTile
                      label="Calls today"
                      value={stats.callsToday.toLocaleString()}
                      accent="text-foreground"
                    />
                    <MetricTile
                      label="Active agents"
                      value={String(agentCount ?? org.botsActive)}
                      accent="text-status-success"
                    />
                    <MetricTile
                      label="Transfer rate"
                      value={`${stats.transferRate}%`}
                      accent="text-brand"
                    />
                    <MetricTile
                      label="Avg. handle time"
                      value={`${stats.avgDurationSec}s`}
                      accent="text-foreground"
                    />
                  </div>

                  <div className="rounded-md border border-surface-border-subtle bg-surface-overlay/40 px-4 py-5 sm:px-5">
                    <div className="mb-4 flex items-center justify-between gap-3">
                      <div>
                        <p className="text-2xs font-semibold uppercase tracking-[0.12em] text-foreground-faint">
                          Conversion
                        </p>
                        <p className="mt-0.5 text-caption text-foreground-muted">
                          Dials → transfer share
                        </p>
                      </div>
                      <Link
                        href="/analytics"
                        className="text-caption font-medium text-brand hover:text-brand-hover"
                      >
                        Open analytics
                      </Link>
                    </div>
                    <ConversionPieChart slices={slices} title="Stages" />
                  </div>

                  <div className="rounded-md border border-surface-border-subtle bg-surface-overlay/40 px-4 py-4">
                    <p className="mb-3 text-2xs font-semibold uppercase tracking-[0.12em] text-foreground-faint">
                      Transfer rate · 7 days
                    </p>
                    <div className="flex h-24 items-end gap-1.5">
                      {transferTrend.map((day) => (
                        <div key={day.day} className="flex min-w-0 flex-1 flex-col items-center gap-1.5">
                          <div className="flex h-16 w-full items-end justify-center">
                            <div
                              className="w-full max-w-[1.75rem] rounded-sm bg-brand/80 transition-all"
                              style={{
                                height: `${Math.max(4, (day.rate / maxTrend) * 100)}%`,
                                opacity: day.rate === 0 ? 0.2 : 1,
                              }}
                              title={`${day.day}: ${day.rate}%`}
                            />
                          </div>
                          <span className="text-2xs text-foreground-faint">{day.day}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              )}

              {section === "live" && (
                <div className="overflow-hidden rounded-md border border-surface-border-subtle">
                  <div className="border-b border-surface-border-subtle bg-surface-overlay/40 px-4 py-2.5">
                    <p className="text-2xs font-semibold uppercase tracking-[0.12em] text-foreground-faint">
                      Live agents — {liveCalls.length}
                    </p>
                  </div>
                  <ul className="divide-y divide-surface-border-subtle">
                    {liveCalls.map((row) => (
                      <li
                        key={`${row.bot}-${row.duration}`}
                        className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-surface-overlay/40"
                      >
                        <span
                          className={cn(
                            "h-2 w-2 shrink-0 rounded-full",
                            STATUS_DOT[row.status] ?? "bg-foreground-faint",
                          )}
                        />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-body font-medium text-foreground">
                            {row.bot}
                          </span>
                          <span className="truncate text-caption text-foreground-faint">
                            {row.campaign}
                          </span>
                        </span>
                        <span className="rounded-sm bg-surface-overlay px-1.5 py-0.5 text-2xs font-medium capitalize text-foreground-muted">
                          {row.status}
                        </span>
                        <span className="w-12 text-right font-mono text-caption tabular-nums text-foreground-faint">
                          {row.duration}
                        </span>
                      </li>
                    ))}
                  </ul>
                  <div className="border-t border-surface-border-subtle px-4 py-3">
                    <Link
                      href="/bots"
                      className="text-caption font-medium text-brand hover:text-brand-hover"
                    >
                      Manage agents →
                    </Link>
                  </div>
                </div>
              )}

              {section === "campaigns" && (
                <div className="overflow-hidden rounded-md border border-surface-border-subtle">
                  <div className="border-b border-surface-border-subtle bg-surface-overlay/40 px-4 py-2.5">
                    <p className="text-2xs font-semibold uppercase tracking-[0.12em] text-foreground-faint">
                      Campaigns — {campaignRows.length}
                    </p>
                  </div>
                  {campaignRows.length === 0 ? (
                    <p className="px-4 py-8 text-center text-caption text-foreground-muted">
                      No campaigns yet.{" "}
                      <Link href="/campaigns/new" className="text-brand hover:text-brand-hover">
                        Create one
                      </Link>
                    </p>
                  ) : (
                    <ul className="divide-y divide-surface-border-subtle">
                      {campaignRows.map((c) => (
                        <li key={c.id}>
                          <Link
                            href={
                              /^[0-9a-f-]{36}$/i.test(c.id)
                                ? `/campaigns/${c.id}`
                                : "/campaigns"
                            }
                            className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-surface-overlay/40"
                          >
                            <span
                              className={cn(
                                "h-2 w-2 shrink-0 rounded-full",
                                STATUS_DOT[c.status] ?? "bg-foreground-faint",
                              )}
                            />
                            <span className="min-w-0 flex-1">
                              <span className="block truncate text-body font-medium text-foreground">
                                {c.name}
                              </span>
                              <span className="text-caption text-foreground-faint">
                                {c.bots} agent{c.bots === 1 ? "" : "s"}
                              </span>
                            </span>
                            <span className="rounded-sm bg-surface-overlay px-1.5 py-0.5 text-2xs font-medium capitalize text-foreground-muted">
                              {c.status}
                            </span>
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )}
                  <div className="border-t border-surface-border-subtle px-4 py-3">
                    <Link
                      href="/campaigns"
                      className="text-caption font-medium text-brand hover:text-brand-hover"
                    >
                      Open campaigns →
                    </Link>
                  </div>
                </div>
              )}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function MiniStat({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent: string;
}) {
  return (
    <div className="rounded-md border border-surface-border-subtle bg-surface-overlay/55 px-3 py-2">
      <p className="text-2xs uppercase tracking-wide text-foreground-faint">{label}</p>
      <p className={cn("mt-0.5 text-lg font-semibold tabular-nums tracking-tight", accent)}>
        {value}
      </p>
    </div>
  );
}

function MetricTile({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent: string;
}) {
  return (
    <div className="rounded-md border border-surface-border-subtle bg-surface-overlay/55 px-4 py-4">
      <p className="text-2xs uppercase tracking-wide text-foreground-faint">{label}</p>
      <p className={cn("mt-1 text-2xl font-semibold tabular-nums tracking-tight", accent)}>
        {value}
      </p>
    </div>
  );
}
