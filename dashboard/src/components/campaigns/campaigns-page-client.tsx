"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  Megaphone,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Search,
  Settings2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toListItem, type CampaignListItem } from "@/lib/campaigns";
import { formatSupabaseError } from "@/lib/errors";
import { readJsonResponse } from "@/lib/fetch-json";
import { createClient, isSupabaseConfigured, supabaseConfigHelp } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";
import type { CampaignRow, CampaignStatus } from "@/lib/types/database";

type StatusFilter = "ALL" | "running" | "paused" | "with_agents" | "no_agents";

const RAIL_KEY = "campaigns.railWidth";
const DETAIL_KEY = "campaigns.detailWidth";
const RAIL_MIN = 180;
const RAIL_MAX = 300;
const DETAIL_MIN = 280;
const DETAIL_MAX = 460;
const RAIL_DEFAULT = 224;
const DETAIL_DEFAULT = 340;

function statusMeta(status: CampaignStatus) {
  if (status === "running") {
    return {
      label: "Running",
      dot: "bg-status-success",
      chip: "text-status-success bg-status-success-muted",
      hint: "Dialing is active — agents can go live",
    };
  }
  return {
    label: "Paused",
    dot: "bg-foreground-faint",
    chip: "text-foreground-muted bg-surface-overlay",
    hint: "Paused — click Run to start dialing",
  };
}

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return (parts[0] ?? "?").slice(0, 2).toUpperCase();
}

function avatarTone(id: string) {
  let hash = 0;
  for (let i = 0; i < id.length; i++) hash = (hash + id.charCodeAt(i) * (i + 1)) % 5;
  const tones = [
    "from-sky-600/40 to-sky-900/50",
    "from-teal-600/40 to-teal-900/50",
    "from-amber-600/35 to-amber-900/50",
    "from-rose-600/35 to-rose-900/50",
    "from-indigo-600/40 to-indigo-900/50",
  ];
  return tones[hash];
}

function readStoredWidth(key: string, fallback: number, min: number, max: number) {
  if (typeof window === "undefined") return fallback;
  const raw = Number(window.localStorage.getItem(key));
  if (!Number.isFinite(raw)) return fallback;
  return Math.min(max, Math.max(min, raw));
}

export function CampaignsPageClient() {
  const [campaigns, setCampaigns] = useState<CampaignListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState("");
  const [hint, setHint] = useState("");
  const [actionError, setActionError] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("ALL");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [railWidth, setRailWidth] = useState(RAIL_DEFAULT);
  const [detailWidth, setDetailWidth] = useState(DETAIL_DEFAULT);
  const railWidthRef = useRef(RAIL_DEFAULT);
  const detailWidthRef = useRef(DETAIL_DEFAULT);
  const dragRef = useRef<{ side: "rail" | "detail"; startX: number; startW: number } | null>(
    null,
  );

  useEffect(() => {
    const rail = readStoredWidth(RAIL_KEY, RAIL_DEFAULT, RAIL_MIN, RAIL_MAX);
    const detail = readStoredWidth(DETAIL_KEY, DETAIL_DEFAULT, DETAIL_MIN, DETAIL_MAX);
    railWidthRef.current = rail;
    detailWidthRef.current = detail;
    setRailWidth(rail);
    setDetailWidth(detail);
  }, []);

  useEffect(() => {
    function onMove(e: MouseEvent) {
      const drag = dragRef.current;
      if (!drag) return;
      const delta = e.clientX - drag.startX;
      if (drag.side === "rail") {
        const next = Math.min(RAIL_MAX, Math.max(RAIL_MIN, drag.startW + delta));
        railWidthRef.current = next;
        setRailWidth(next);
      } else {
        const next = Math.min(DETAIL_MAX, Math.max(DETAIL_MIN, drag.startW - delta));
        detailWidthRef.current = next;
        setDetailWidth(next);
      }
    }
    function onUp() {
      const drag = dragRef.current;
      if (!drag) return;
      dragRef.current = null;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      if (drag.side === "rail") {
        window.localStorage.setItem(RAIL_KEY, String(railWidthRef.current));
      } else {
        window.localStorage.setItem(DETAIL_KEY, String(detailWidthRef.current));
      }
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  function startResize(side: "rail" | "detail", e: React.MouseEvent) {
    e.preventDefault();
    dragRef.current = {
      side,
      startX: e.clientX,
      startW: side === "rail" ? railWidthRef.current : detailWidthRef.current,
    };
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }

  const loadCampaigns = useCallback(async (opts?: { quiet?: boolean }) => {
    if (!isSupabaseConfigured()) {
      setError(supabaseConfigHelp());
      setLoading(false);
      return;
    }

    if (!opts?.quiet) setSyncing(true);
    setError("");

    try {
      const supabase = createClient();
      const { data: rows, error: campaignsError } = await supabase
        .from("campaigns")
        .select("id, name, status, script_json")
        .order("name", { ascending: true });

      if (campaignsError) throw campaignsError;

      let botCounts: Record<string, number> = {};
      const { data: bots, error: botsError } = await supabase.from("bots").select("campaign_id");
      if (!botsError) {
        botCounts = (bots ?? []).reduce<Record<string, number>>((acc, bot) => {
          if (bot.campaign_id) {
            acc[bot.campaign_id] = (acc[bot.campaign_id] ?? 0) + 1;
          }
          return acc;
        }, {});
      }

      const next = ((rows ?? []) as CampaignRow[]).map((row) =>
        toListItem(row, botCounts[row.id] ?? 0),
      );
      setCampaigns(next);
      setHint(`Synced — ${next.length} campaign${next.length === 1 ? "" : "s"}`);
      setSelectedId((prev) => {
        if (prev && next.some((c) => c.id === prev)) return prev;
        return next[0]?.id ?? null;
      });
    } catch (err) {
      setError(formatSupabaseError(err, "Could not load campaigns."));
    } finally {
      setSyncing(false);
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadCampaigns({ quiet: true });
  }, [loadCampaigns]);

  const counts = useMemo(() => {
    let running = 0;
    let paused = 0;
    let withAgents = 0;
    let noAgents = 0;
    for (const c of campaigns) {
      if (c.status === "running") running += 1;
      else paused += 1;
      if (c.bots > 0) withAgents += 1;
      else noAgents += 1;
    }
    return { total: campaigns.length, running, paused, withAgents, noAgents };
  }, [campaigns]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return campaigns.filter((c) => {
      if (statusFilter === "running" && c.status !== "running") return false;
      if (statusFilter === "paused" && c.status !== "paused") return false;
      if (statusFilter === "with_agents" && c.bots === 0) return false;
      if (statusFilter === "no_agents" && c.bots > 0) return false;
      if (!q) return true;
      return (
        c.name.toLowerCase().includes(q) ||
        c.script.toLowerCase().includes(q)
      );
    });
  }, [campaigns, search, statusFilter]);

  useEffect(() => {
    if (!filtered.length) {
      setSelectedId(null);
      return;
    }
    if (!selectedId || !filtered.some((c) => c.id === selectedId)) {
      setSelectedId(filtered[0].id);
    }
  }, [filtered, selectedId]);

  const selected = useMemo(
    () => filtered.find((c) => c.id === selectedId) ?? null,
    [filtered, selectedId],
  );

  async function toggleCampaignStatus(campaign: CampaignListItem) {
    setActionError("");
    setBusyId(campaign.id);

    try {
      const starting = campaign.status !== "running";
      if (starting && campaign.bots === 0) {
        throw new Error(`Assign at least one agent to "${campaign.name}" before running.`);
      }

      const action = starting ? "start" : "stop";
      const res = await fetch(`/api/campaigns/${campaign.id}/run`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action }),
      });
      const data = await readJsonResponse<{
        error?: string;
        status?: CampaignStatus;
        message?: string;
        detail?: string;
      }>(res);

      if (!res.ok) {
        throw new Error(data.error ?? "Could not update campaign.");
      }

      const nextStatus: CampaignStatus =
        data.status ?? (starting ? "running" : "paused");
      setCampaigns((prev) =>
        prev.map((c) => (c.id === campaign.id ? { ...c, status: nextStatus } : c)),
      );
      setHint(
        data.message ??
          data.detail ??
          (nextStatus === "running"
            ? `Running ${campaign.name}.`
            : `Paused ${campaign.name}.`),
      );
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : formatSupabaseError(err, "Could not update campaign."),
      );
    } finally {
      setBusyId(null);
    }
  }

  const filterLabel =
    statusFilter === "ALL"
      ? "All campaigns"
      : statusFilter === "running"
        ? "Running"
        : statusFilter === "paused"
          ? "Paused"
          : statusFilter === "with_agents"
            ? "With agents"
            : "No agents";

  return (
    <div className="campaigns-shell relative flex h-full min-h-0 flex-1 flex-col overflow-hidden bg-surface-raised">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_80%_50%_at_0%_0%,rgba(59,130,246,0.12),transparent_55%),radial-gradient(ellipse_60%_40%_at_100%_100%,rgba(15,23,42,0.85),transparent_55%)]"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.28] [background-image:linear-gradient(rgba(255,255,255,0.028)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.028)_1px,transparent_1px)] [background-size:40px_40px] [mask-image:radial-gradient(ellipse_at_center,black_40%,transparent_85%)]"
      />

      <div className="relative flex min-h-0 flex-1 flex-col lg:flex-row">
        <aside
          className="campaigns-rail flex w-full shrink-0 flex-col border-b border-surface-border-subtle bg-surface/75 backdrop-blur-md lg:h-full lg:overflow-hidden lg:border-b-0 lg:border-r"
          style={{ ["--campaigns-rail" as string]: `${railWidth}px` }}
        >
          <div className="border-b border-surface-border-subtle px-4 py-4">
            <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-foreground-faint">
              Management
            </p>
            <h1 className="mt-1 text-lg font-semibold tracking-tight text-foreground">Campaigns</h1>
            <p className="mt-1 truncate text-caption text-foreground-muted">
              {counts.total} total
            </p>
          </div>

          <nav className="flex gap-1 overflow-x-auto p-2 scrollbar-thin lg:min-h-0 lg:flex-1 lg:flex-col lg:overflow-y-auto">
            <FilterChip
              active={statusFilter === "ALL"}
              label="Everyone"
              count={counts.total}
              onClick={() => setStatusFilter("ALL")}
              icon={<Megaphone className="h-3.5 w-3.5 shrink-0 text-foreground-faint" />}
            />
            <FilterChip
              active={statusFilter === "running"}
              label="Running"
              count={counts.running}
              onClick={() => setStatusFilter("running")}
              dotClass="bg-status-success"
            />
            <FilterChip
              active={statusFilter === "paused"}
              label="Paused"
              count={counts.paused}
              onClick={() => setStatusFilter("paused")}
              dotClass="bg-foreground-faint"
            />
            <FilterChip
              active={statusFilter === "with_agents"}
              label="With agents"
              count={counts.withAgents}
              onClick={() => setStatusFilter("with_agents")}
              dotClass="bg-brand"
            />
            <FilterChip
              active={statusFilter === "no_agents"}
              label="No agents"
              count={counts.noAgents}
              onClick={() => setStatusFilter("no_agents")}
              dotClass="bg-status-warning"
            />
          </nav>

          <div className="mt-auto hidden space-y-2 border-t border-surface-border-subtle p-3 lg:block">
            <MiniStat label="Running" value={counts.running} accent="text-status-success" />
            <MiniStat label="Paused" value={counts.paused} accent="text-foreground-muted" />
            <MiniStat label="Total" value={counts.total} accent="text-foreground" />
          </div>
        </aside>

        <ResizeHandle className="hidden lg:flex" onMouseDown={(e) => startResize("rail", e)} />

        <section className="flex min-h-0 min-w-0 flex-1 flex-col">
          <header className="flex flex-col gap-3 border-b border-surface-border-subtle bg-surface-raised/80 px-4 py-3 backdrop-blur-md sm:flex-row sm:items-center sm:justify-between">
            <div className="relative min-w-0 flex-1 sm:max-w-md">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-foreground-faint" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search campaign or script"
                className="h-10 border-transparent bg-surface-overlay pl-10 text-body placeholder:text-foreground-faint focus:border-brand/40"
              />
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <Button variant="secondary" size="sm" href="/campaigns/new">
                <Plus className="h-3.5 w-3.5" />
                New
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() => void loadCampaigns()}
                disabled={syncing}
              >
                <RefreshCw className={cn("h-3.5 w-3.5", syncing && "animate-spin")} />
                {syncing ? "Syncing…" : "Sync"}
              </Button>
            </div>
          </header>

          <div className="flex gap-2 overflow-x-auto border-b border-surface-border-subtle px-4 py-3 scrollbar-thin lg:hidden">
            <MiniStat label="Running" value={counts.running} accent="text-status-success" />
            <MiniStat label="Paused" value={counts.paused} accent="text-foreground-muted" />
            <MiniStat label="Total" value={counts.total} accent="text-foreground" />
          </div>

          {(error || actionError || hint) && (
            <div className="space-y-2 px-4 pt-3">
              {error && (
                <p className="rounded-md border border-status-danger/30 bg-status-danger-muted px-3 py-2 text-caption text-status-danger">
                  {error}
                </p>
              )}
              {actionError && (
                <p className="rounded-md border border-status-danger/30 bg-status-danger-muted px-3 py-2 text-caption text-status-danger">
                  {actionError}
                </p>
              )}
              {!error && !actionError && hint && (
                <p className="rounded-md border border-surface-border bg-surface-overlay/80 px-3 py-2 text-caption text-foreground-muted">
                  {hint}
                </p>
              )}
            </div>
          )}

          <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
            <div className="min-h-0 flex-1 overflow-y-auto scrollbar-thin">
              <div className="sticky top-0 z-10 flex items-center justify-between bg-surface-raised/92 px-4 py-2 backdrop-blur-sm">
                <p className="text-2xs font-semibold uppercase tracking-[0.12em] text-foreground-faint">
                  {filterLabel}
                  <span className="ml-2 font-medium text-foreground-muted">— {filtered.length}</span>
                </p>
                <Megaphone className="h-3.5 w-3.5 text-foreground-faint" />
              </div>

              {loading ? (
                <div className="space-y-2 px-3 py-4">
                  {Array.from({ length: 6 }).map((_, i) => (
                    <div
                      key={i}
                      className="h-14 animate-pulse rounded-md bg-surface-overlay/80"
                      style={{ animationDelay: `${i * 50}ms` }}
                    />
                  ))}
                </div>
              ) : filtered.length === 0 ? (
                <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
                  <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-surface-overlay ring-1 ring-surface-border">
                    <Megaphone className="h-5 w-5 text-foreground-faint" />
                  </div>
                  <p className="text-body font-medium text-foreground-secondary">No campaigns here</p>
                  <p className="mt-1 max-w-xs text-caption text-foreground-faint">
                    Create an outbound campaign to configure scripts, knowledge base, and agents.
                  </p>
                  <Button className="mt-4" size="sm" href="/campaigns/new">
                    <Plus className="h-3.5 w-3.5" />
                    New campaign
                  </Button>
                </div>
              ) : (
                <ul className="space-y-0.5 px-2 pb-4 pt-1">
                  {filtered.map((campaign, index) => {
                    const meta = statusMeta(campaign.status);
                    const active = selected?.id === campaign.id;
                    return (
                      <li
                        key={campaign.id}
                        className="campaigns-row"
                        style={{ animationDelay: `${Math.min(index, 12) * 28}ms` }}
                      >
                        <button
                          type="button"
                          onClick={() => setSelectedId(campaign.id)}
                          className={cn(
                            "group flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left transition-[background-color,color,box-shadow] duration-150",
                            active
                              ? "bg-surface-overlay text-foreground shadow-[inset_2px_0_0_0_var(--brand)]"
                              : "text-foreground-secondary hover:bg-surface-overlay/70 hover:text-foreground",
                          )}
                        >
                          <span className="relative shrink-0">
                            <span
                              className={cn(
                                "flex h-9 w-9 items-center justify-center rounded-[10px] bg-gradient-to-br text-caption font-semibold text-foreground ring-1 ring-white/5",
                                avatarTone(campaign.id),
                              )}
                            >
                              {initials(campaign.name)}
                            </span>
                            <span
                              className={cn(
                                "absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-surface-raised",
                                meta.dot,
                              )}
                              title={meta.label}
                            />
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="flex items-center gap-2">
                              <span className="truncate text-body font-medium text-foreground">
                                {campaign.name}
                              </span>
                              <span
                                className={cn(
                                  "hidden shrink-0 rounded-sm px-1.5 py-0.5 text-2xs font-medium sm:inline",
                                  meta.chip,
                                )}
                              >
                                {meta.label}
                              </span>
                            </span>
                            <span className="mt-0.5 flex items-center gap-2 text-caption text-foreground-faint">
                              <span className="truncate">{campaign.script}</span>
                              <span>·</span>
                              <span>
                                {campaign.bots} agent{campaign.bots === 1 ? "" : "s"}
                              </span>
                            </span>
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>

            <ResizeHandle className="hidden lg:flex" onMouseDown={(e) => startResize("detail", e)} />

            <aside
              className="hidden shrink-0 border-t border-surface-border-subtle bg-surface/55 backdrop-blur-sm lg:flex lg:h-full lg:flex-col lg:overflow-y-auto lg:border-l lg:border-t-0"
              style={{ width: detailWidth, minWidth: detailWidth }}
            >
              {selected ? (
                <CampaignDetail
                  campaign={selected}
                  busy={busyId === selected.id}
                  onToggle={() => void toggleCampaignStatus(selected)}
                />
              ) : (
                <div className="flex h-full items-center justify-center p-6 text-center text-caption text-foreground-faint">
                  Select a campaign
                </div>
              )}
            </aside>
          </div>

          {selected && (
            <div className="shrink-0 border-t border-surface-border-subtle bg-surface/70 lg:hidden">
              <CampaignDetail
                campaign={selected}
                busy={busyId === selected.id}
                onToggle={() => void toggleCampaignStatus(selected)}
                compact
              />
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function ResizeHandle({
  className,
  onMouseDown,
}: {
  className?: string;
  onMouseDown: (e: React.MouseEvent) => void;
}) {
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      onMouseDown={onMouseDown}
      className={cn(
        "group relative z-20 w-1.5 shrink-0 cursor-col-resize items-stretch justify-center bg-transparent transition-colors hover:bg-brand/20",
        className,
      )}
      title="Drag to resize"
    >
      <span className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-surface-border-subtle group-hover:bg-brand/50" />
    </div>
  );
}

function FilterChip({
  active,
  label,
  count,
  dotClass,
  icon,
  onClick,
}: {
  active: boolean;
  label: string;
  count: number;
  dotClass?: string;
  icon?: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex shrink-0 items-center gap-2 rounded-md px-3 py-2 text-left text-caption font-medium transition-colors duration-150 lg:w-full",
        active
          ? "bg-surface-overlay text-foreground shadow-[inset_2px_0_0_0_var(--brand)]"
          : "text-foreground-muted hover:bg-surface-overlay/60 hover:text-foreground-secondary",
      )}
    >
      {dotClass ? <span className={cn("h-2 w-2 shrink-0 rounded-full", dotClass)} /> : icon}
      <span className="min-w-0 flex-1 truncate">{label}</span>
      <span className="tabular-nums text-foreground-faint">{count}</span>
    </button>
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
    <div className="min-w-[5.5rem] rounded-md border border-surface-border-subtle bg-surface-overlay/55 px-3 py-2">
      <p className="text-2xs uppercase tracking-wide text-foreground-faint">{label}</p>
      <p className={cn("mt-0.5 text-lg font-semibold tabular-nums tracking-tight", accent)}>
        {value}
      </p>
    </div>
  );
}

function CampaignDetail({
  campaign,
  busy,
  onToggle,
  compact,
}: {
  campaign: CampaignListItem;
  busy: boolean;
  onToggle: () => void;
  compact?: boolean;
}) {
  const meta = statusMeta(campaign.status);
  const running = campaign.status === "running";

  return (
    <div className={cn("flex h-full flex-col", compact ? "p-4" : "p-5")}>
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "relative flex h-14 w-14 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br text-base font-semibold text-foreground ring-1 ring-white/5",
            avatarTone(campaign.id),
          )}
        >
          {initials(campaign.name)}
          <span
            className={cn(
              "absolute bottom-0 right-0 h-3.5 w-3.5 rounded-full border-[3px] border-surface",
              meta.dot,
            )}
          />
        </span>
        <div className="min-w-0 pt-0.5">
          <p className="truncate text-base font-semibold text-foreground">{campaign.name}</p>
          <p className="mt-0.5 truncate text-caption text-foreground-muted">{campaign.script}</p>
          <span
            className={cn(
              "mt-2 inline-flex rounded-sm px-2 py-0.5 text-2xs font-medium",
              meta.chip,
            )}
          >
            {meta.label}
          </span>
        </div>
      </div>

      <p className="mt-4 text-caption text-foreground-faint">{meta.hint}</p>

      <dl className="mt-5 space-y-3 border-t border-surface-border-subtle pt-4">
        <DetailRow label="Agents" value={String(campaign.bots)} />
        <DetailRow
          label="Dials"
          value={campaign.dials ? campaign.dials.toLocaleString() : "—"}
        />
        <DetailRow
          label="Transfer rate"
          value={campaign.transferRate ? `${campaign.transferRate}%` : "—"}
        />
      </dl>

      <div className="mt-auto space-y-2 pt-5">
        {running ? (
          <Button
            className="w-full"
            variant="secondary"
            disabled={busy}
            onClick={onToggle}
          >
            <Pause className={cn("h-4 w-4", busy && "animate-pulse")} />
            {busy ? "Pausing…" : "Pause"}
          </Button>
        ) : (
          <Button
            className="w-full"
            disabled={busy || campaign.bots === 0}
            onClick={onToggle}
          >
            <Play className={cn("h-4 w-4", busy && "animate-pulse")} />
            {busy ? "Starting…" : "Run"}
          </Button>
        )}
        <Button className="w-full" variant="secondary" href={`/campaigns/${campaign.id}`}>
          <Settings2 className="h-4 w-4" />
          Edit campaign
        </Button>
        {campaign.bots === 0 && !running && (
          <p className="text-center text-2xs text-foreground-faint">
            Assign an agent first —{" "}
            <Link href="/bots" className="text-brand hover:text-brand-hover">
              Agents
            </Link>
          </p>
        )}
      </div>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-caption text-foreground-faint">{label}</dt>
      <dd className="truncate text-caption text-foreground-secondary">{value}</dd>
    </div>
  );
}
