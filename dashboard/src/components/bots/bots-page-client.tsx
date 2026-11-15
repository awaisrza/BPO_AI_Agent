"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Bot, Plus, RefreshCw, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { ProgressBar } from "@/components/ui/progress-bar";
import { botStatusForCampaign } from "@/lib/campaigns";
import { formatSupabaseError } from "@/lib/errors";
import { createClient, isSupabaseConfigured, supabaseConfigHelp } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";
import type { BotStatus, CampaignStatus } from "@/lib/types/database";

type CampaignOption = {
  id: string;
  name: string;
  status: CampaignStatus;
};

type BotListItem = {
  id: string;
  name: string;
  status: BotStatus;
  campaignId: string | null;
  campaignName: string;
  campaignStatus: CampaignStatus | null;
  vicidialAgentUser: string;
};

type StatusFilter = "ALL" | BotStatus | "assigned" | "unassigned";

const RAIL_KEY = "bots.railWidth";
const DETAIL_KEY = "bots.detailWidth";
const RAIL_MIN = 180;
const RAIL_MAX = 300;
const DETAIL_MIN = 280;
const DETAIL_MAX = 480;
const RAIL_DEFAULT = 224;
const DETAIL_DEFAULT = 340;

const STATUS_META: Record<
  BotStatus,
  { label: string; dot: string; chip: string; hint: string }
> = {
  live: {
    label: "On call",
    dot: "bg-status-success",
    chip: "text-status-success bg-status-success-muted",
    hint: "Handling a live call",
  },
  ringing: {
    label: "Ringing",
    dot: "bg-status-warning",
    chip: "text-status-warning bg-status-warning-muted",
    hint: "Outbound ringing",
  },
  dialing: {
    label: "Dialing",
    dot: "bg-status-info",
    chip: "text-status-info bg-status-info-muted",
    hint: "Dialing in progress",
  },
  idle: {
    label: "Ready",
    dot: "bg-status-success",
    chip: "text-status-success bg-status-success-muted",
    hint: "Ready — campaign is running",
  },
  offline: {
    label: "Offline",
    dot: "bg-foreground-faint",
    chip: "text-foreground-muted bg-surface-overlay",
    hint: "Not live — assign a campaign and click Run",
  },
};

function statusMeta(status: BotStatus) {
  return STATUS_META[status] ?? STATUS_META.offline;
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

export function BotsPageClient() {
  const [bots, setBots] = useState<BotListItem[]>([]);
  const [campaigns, setCampaigns] = useState<CampaignOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState("");
  const [hint, setHint] = useState("");
  const [actionError, setActionError] = useState("");
  const [busyBotId, setBusyBotId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("ALL");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [viciDraft, setViciDraft] = useState("");
  const [plan, setPlan] = useState("Pilot");
  const [included, setIncluded] = useState(10);
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

  const loadBots = useCallback(async (opts?: { quiet?: boolean }) => {
    if (!isSupabaseConfigured()) {
      setError(supabaseConfigHelp());
      setLoading(false);
      return;
    }

    if (!opts?.quiet) setSyncing(true);
    setError("");

    try {
      const supabase = createClient();

      const [
        { data: botRows, error: botsError },
        { data: campaignRows, error: campaignsError },
        { data: profile },
      ] = await Promise.all([
        supabase
          .from("bots")
          .select("id, name, status, campaign_id, vicidial_agent_user")
          .order("name", { ascending: true }),
        supabase.from("campaigns").select("id, name, status").order("name"),
        supabase.from("profiles").select("org_id").maybeSingle(),
      ]);

      if (botsError) throw botsError;
      if (campaignsError) throw campaignsError;

      if (profile?.org_id) {
        const { data: org } = await supabase
          .from("organizations")
          .select("plan, bots_included")
          .eq("id", profile.org_id)
          .single();
        if (org) {
          setPlan(org.plan ?? "Pilot");
          setIncluded(org.bots_included ?? 10);
        }
      }

      const campaignMap = Object.fromEntries(
        (campaignRows ?? []).map((c) => [
          c.id,
          { name: c.name, status: c.status as CampaignStatus },
        ]),
      );

      setCampaigns(
        (campaignRows ?? []).map((c) => ({
          id: c.id,
          name: c.name,
          status: c.status as CampaignStatus,
        })),
      );

      const next = (botRows ?? []).map((bot) => {
        const campaign = bot.campaign_id ? campaignMap[bot.campaign_id] : null;
        return {
          id: bot.id,
          name: bot.name,
          status: bot.status as BotStatus,
          campaignId: bot.campaign_id,
          campaignName: campaign?.name ?? "—",
          campaignStatus: campaign?.status ?? null,
          vicidialAgentUser: bot.vicidial_agent_user ?? "",
        };
      });

      setBots(next);
      setHint(`Synced — ${next.length} agent${next.length === 1 ? "" : "s"}`);
      setSelectedId((prev) => {
        if (prev && next.some((b) => b.id === prev)) return prev;
        return next[0]?.id ?? null;
      });
    } catch (err) {
      setError(formatSupabaseError(err, "Could not load agents."));
    } finally {
      setSyncing(false);
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadBots({ quiet: true });
  }, [loadBots]);

  const counts = useMemo(() => {
    const byStatus: Record<BotStatus, number> = {
      live: 0,
      ringing: 0,
      dialing: 0,
      idle: 0,
      offline: 0,
    };
    let assigned = 0;
    let unassigned = 0;
    for (const bot of bots) {
      byStatus[bot.status] = (byStatus[bot.status] ?? 0) + 1;
      if (bot.campaignId) assigned += 1;
      else unassigned += 1;
    }
    return { byStatus, assigned, unassigned, total: bots.length };
  }, [bots]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return bots.filter((bot) => {
      if (statusFilter === "assigned" && !bot.campaignId) return false;
      if (statusFilter === "unassigned" && bot.campaignId) return false;
      if (
        statusFilter !== "ALL" &&
        statusFilter !== "assigned" &&
        statusFilter !== "unassigned" &&
        bot.status !== statusFilter
      ) {
        return false;
      }
      if (!q) return true;
      return (
        bot.name.toLowerCase().includes(q) ||
        bot.vicidialAgentUser.toLowerCase().includes(q) ||
        bot.campaignName.toLowerCase().includes(q)
      );
    });
  }, [bots, search, statusFilter]);

  useEffect(() => {
    if (!filtered.length) {
      setSelectedId(null);
      return;
    }
    if (!selectedId || !filtered.some((b) => b.id === selectedId)) {
      setSelectedId(filtered[0].id);
    }
  }, [filtered, selectedId]);

  const selected = useMemo(
    () => filtered.find((b) => b.id === selectedId) ?? null,
    [filtered, selectedId],
  );

  useEffect(() => {
    setViciDraft(selected?.vicidialAgentUser ?? "");
    setActionError("");
  }, [selected?.id, selected?.vicidialAgentUser]);

  async function updateVicidialUser(botId: string, vicidialAgentUser: string) {
    setActionError("");
    setBusyBotId(botId);
    try {
      const supabase = createClient();
      const { error: updateError } = await supabase
        .from("bots")
        .update({ vicidial_agent_user: vicidialAgentUser.trim() || null })
        .eq("id", botId);
      if (updateError) throw updateError;
      setBots((prev) =>
        prev.map((bot) =>
          bot.id === botId ? { ...bot, vicidialAgentUser: vicidialAgentUser.trim() } : bot,
        ),
      );
      setHint(`Updated ViciDial login for agent.`);
    } catch (err) {
      setActionError(formatSupabaseError(err, "Could not update ViciDial login."));
    } finally {
      setBusyBotId(null);
    }
  }

  async function reassignCampaign(botId: string, campaignId: string) {
    setActionError("");
    setBusyBotId(botId);
    try {
      const campaign = campaigns.find((c) => c.id === campaignId);
      const nextStatus = campaign ? botStatusForCampaign(campaign.status) : "offline";
      const supabase = createClient();
      const { error: updateError } = await supabase
        .from("bots")
        .update({ campaign_id: campaignId, status: nextStatus })
        .eq("id", botId);
      if (updateError) throw updateError;
      setBots((prev) =>
        prev.map((bot) =>
          bot.id === botId
            ? {
                ...bot,
                campaignId,
                campaignName: campaign?.name ?? "—",
                campaignStatus: campaign?.status ?? null,
                status: nextStatus,
              }
            : bot,
        ),
      );
      setHint(`Reassigned to ${campaign?.name ?? "campaign"}.`);
    } catch (err) {
      setActionError(formatSupabaseError(err, "Could not reassign agent."));
    } finally {
      setBusyBotId(null);
    }
  }

  const filterLabel =
    statusFilter === "ALL"
      ? "All agents"
      : statusFilter === "assigned"
        ? "Assigned"
        : statusFilter === "unassigned"
          ? "Unassigned"
          : statusMeta(statusFilter).label;

  const readyCount = counts.byStatus.idle + counts.byStatus.live + counts.byStatus.dialing + counts.byStatus.ringing;

  return (
    <div className="bots-shell relative flex h-full min-h-0 flex-1 flex-col overflow-hidden bg-surface-raised">
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
          className="bots-rail flex w-full shrink-0 flex-col border-b border-surface-border-subtle bg-surface/75 backdrop-blur-md lg:h-full lg:overflow-hidden lg:border-b-0 lg:border-r"
          style={{ ["--bots-rail" as string]: `${railWidth}px` }}
        >
          <div className="border-b border-surface-border-subtle px-4 py-4">
            <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-foreground-faint">
              Fleet
            </p>
            <h1 className="mt-1 text-lg font-semibold tracking-tight text-foreground">Agents</h1>
            <p className="mt-1 truncate text-caption text-foreground-muted">
              {counts.total} in roster
            </p>
          </div>

          <nav className="flex gap-1 overflow-x-auto p-2 scrollbar-thin lg:min-h-0 lg:flex-1 lg:flex-col lg:overflow-y-auto">
            <FilterChip
              active={statusFilter === "ALL"}
              label="Everyone"
              count={counts.total}
              onClick={() => setStatusFilter("ALL")}
              icon={<Bot className="h-3.5 w-3.5 shrink-0 text-foreground-faint" />}
            />
            <FilterChip
              active={statusFilter === "live"}
              label="On call"
              count={counts.byStatus.live}
              onClick={() => setStatusFilter("live")}
              dotClass={STATUS_META.live.dot}
            />
            <FilterChip
              active={statusFilter === "idle"}
              label="Ready"
              count={counts.byStatus.idle}
              onClick={() => setStatusFilter("idle")}
              dotClass={STATUS_META.idle.dot}
            />
            <FilterChip
              active={statusFilter === "dialing"}
              label="Dialing"
              count={counts.byStatus.dialing}
              onClick={() => setStatusFilter("dialing")}
              dotClass={STATUS_META.dialing.dot}
            />
            <FilterChip
              active={statusFilter === "ringing"}
              label="Ringing"
              count={counts.byStatus.ringing}
              onClick={() => setStatusFilter("ringing")}
              dotClass={STATUS_META.ringing.dot}
            />
            <FilterChip
              active={statusFilter === "offline"}
              label="Offline"
              count={counts.byStatus.offline}
              onClick={() => setStatusFilter("offline")}
              dotClass={STATUS_META.offline.dot}
            />
            <FilterChip
              active={statusFilter === "assigned"}
              label="Assigned"
              count={counts.assigned}
              onClick={() => setStatusFilter("assigned")}
              dotClass="bg-brand"
            />
            <FilterChip
              active={statusFilter === "unassigned"}
              label="Unassigned"
              count={counts.unassigned}
              onClick={() => setStatusFilter("unassigned")}
              dotClass="bg-status-warning"
            />
          </nav>

          <div className="mt-auto hidden space-y-3 border-t border-surface-border-subtle p-3 lg:block">
            <ProgressBar
              value={bots.length}
              max={Math.max(included, 1)}
              label={`${plan} plan`}
              sublabel={`${Math.max(0, included - bots.length)} left`}
            />
            <MiniStat label="Live / ready" value={readyCount} accent="text-status-success" />
            <MiniStat label="Offline" value={counts.byStatus.offline} accent="text-foreground-muted" />
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
                placeholder="Search agent, login, campaign"
                className="h-10 border-transparent bg-surface-overlay pl-10 text-body placeholder:text-foreground-faint focus:border-brand/40"
              />
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <Button variant="secondary" size="sm" href="/bots/assign">
                <Plus className="h-3.5 w-3.5" />
                Assign
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() => void loadBots()}
                disabled={syncing}
              >
                <RefreshCw className={cn("h-3.5 w-3.5", syncing && "animate-spin")} />
                {syncing ? "Syncing…" : "Sync"}
              </Button>
            </div>
          </header>

          <div className="space-y-2 border-b border-surface-border-subtle px-4 py-3 lg:hidden">
            <ProgressBar
              value={bots.length}
              max={Math.max(included, 1)}
              label={`${plan} plan`}
              sublabel={`${Math.max(0, included - bots.length)} left`}
            />
            <div className="flex gap-2 overflow-x-auto scrollbar-thin">
              <MiniStat label="Live / ready" value={readyCount} accent="text-status-success" />
              <MiniStat label="Offline" value={counts.byStatus.offline} accent="text-foreground-muted" />
              <MiniStat label="Total" value={counts.total} accent="text-foreground" />
            </div>
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

          <div className="mx-4 mt-3 rounded-md border border-brand/20 bg-brand-muted/40 px-3 py-2 text-caption text-foreground-secondary">
            Assign each agent to a campaign, then open <span className="text-foreground">Campaigns</span> and
            click <span className="text-foreground">Run</span> — assigned agents go live automatically.
          </div>

          <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
            <div className="min-h-0 flex-1 overflow-y-auto scrollbar-thin">
              <div className="sticky top-0 z-10 flex items-center justify-between bg-surface-raised/92 px-4 py-2 backdrop-blur-sm">
                <p className="text-2xs font-semibold uppercase tracking-[0.12em] text-foreground-faint">
                  {filterLabel}
                  <span className="ml-2 font-medium text-foreground-muted">— {filtered.length}</span>
                </p>
                <Bot className="h-3.5 w-3.5 text-foreground-faint" />
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
                    <Bot className="h-5 w-5 text-foreground-faint" />
                  </div>
                  <p className="text-body font-medium text-foreground-secondary">No agents here</p>
                  <p className="mt-1 max-w-xs text-caption text-foreground-faint">
                    Assign AI agents to campaigns to start handling outbound calls.
                  </p>
                  <Button className="mt-4" variant="secondary" size="sm" href="/bots/assign">
                    <Plus className="h-3.5 w-3.5" />
                    Assign to campaign
                  </Button>
                </div>
              ) : (
                <ul className="space-y-0.5 px-2 pb-4 pt-1">
                  {filtered.map((bot, index) => {
                    const meta = statusMeta(bot.status);
                    const active = selected?.id === bot.id;
                    return (
                      <li
                        key={bot.id}
                        className="bots-row"
                        style={{ animationDelay: `${Math.min(index, 12) * 28}ms` }}
                      >
                        <button
                          type="button"
                          onClick={() => setSelectedId(bot.id)}
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
                                avatarTone(bot.id),
                              )}
                            >
                              {initials(bot.name)}
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
                                {bot.name}
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
                              <span className="truncate font-mono">
                                {bot.vicidialAgentUser || "no login"}
                              </span>
                              <span>·</span>
                              <span className="truncate">{bot.campaignName}</span>
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
                <BotDetail
                  bot={selected}
                  campaigns={campaigns}
                  busy={busyBotId === selected.id}
                  viciDraft={viciDraft}
                  onViciDraftChange={setViciDraft}
                  onSaveVici={() => {
                    const next = viciDraft.trim();
                    if (next !== selected.vicidialAgentUser) {
                      void updateVicidialUser(selected.id, next);
                    }
                  }}
                  onReassign={(campaignId) => void reassignCampaign(selected.id, campaignId)}
                />
              ) : (
                <div className="flex h-full items-center justify-center p-6 text-center text-caption text-foreground-faint">
                  Select an agent
                </div>
              )}
            </aside>
          </div>

          {selected && (
            <div className="shrink-0 border-t border-surface-border-subtle bg-surface/70 lg:hidden">
              <BotDetail
                bot={selected}
                campaigns={campaigns}
                busy={busyBotId === selected.id}
                viciDraft={viciDraft}
                onViciDraftChange={setViciDraft}
                onSaveVici={() => {
                  const next = viciDraft.trim();
                  if (next !== selected.vicidialAgentUser) {
                    void updateVicidialUser(selected.id, next);
                  }
                }}
                onReassign={(campaignId) => void reassignCampaign(selected.id, campaignId)}
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

function BotDetail({
  bot,
  campaigns,
  busy,
  viciDraft,
  onViciDraftChange,
  onSaveVici,
  onReassign,
  compact,
}: {
  bot: BotListItem;
  campaigns: CampaignOption[];
  busy: boolean;
  viciDraft: string;
  onViciDraftChange: (v: string) => void;
  onSaveVici: () => void;
  onReassign: (campaignId: string) => void;
  compact?: boolean;
}) {
  const meta = statusMeta(bot.status);
  return (
    <div className={cn("flex h-full flex-col", compact ? "p-4" : "p-5")}>
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "relative flex h-14 w-14 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br text-base font-semibold text-foreground ring-1 ring-white/5",
            avatarTone(bot.id),
          )}
        >
          {initials(bot.name)}
          <span
            className={cn(
              "absolute bottom-0 right-0 h-3.5 w-3.5 rounded-full border-[3px] border-surface",
              meta.dot,
            )}
          />
        </span>
        <div className="min-w-0 pt-0.5">
          <p className="truncate text-base font-semibold text-foreground">{bot.name}</p>
          <p className="mt-0.5 truncate text-caption text-foreground-muted">{bot.campaignName}</p>
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

      <div className="mt-5 space-y-4 border-t border-surface-border-subtle pt-4">
        <label className="block space-y-1.5">
          <span className="text-caption text-foreground-faint">ViciDial login</span>
          <Input
            className="font-mono"
            value={viciDraft}
            disabled={busy}
            placeholder="6666"
            onChange={(e) => onViciDraftChange(e.target.value)}
            onBlur={onSaveVici}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.currentTarget.blur();
              }
            }}
          />
        </label>

        <label className="block space-y-1.5">
          <span className="text-caption text-foreground-faint">Campaign</span>
          {campaigns.length === 0 ? (
            <p className="text-caption text-foreground-muted">No campaigns yet</p>
          ) : (
            <Select
              value={bot.campaignId ?? ""}
              disabled={busy}
              onChange={(e) => onReassign(e.target.value)}
            >
              {!bot.campaignId && (
                <option value="" disabled>
                  Select campaign
                </option>
              )}
              {campaigns.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                  {c.status === "running" ? " · Running" : ""}
                </option>
              ))}
            </Select>
          )}
        </label>

        <dl className="space-y-3">
          <DetailRow label="Agent ID" value={bot.id.slice(0, 8)} mono />
          <DetailRow
            label="Campaign status"
            value={bot.campaignStatus ?? "—"}
          />
        </dl>
      </div>
    </div>
  );
}

function DetailRow({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-caption text-foreground-faint">{label}</dt>
      <dd
        className={cn(
          "truncate text-caption text-foreground-secondary",
          mono && "font-mono",
        )}
      >
        {value}
      </dd>
    </div>
  );
}
