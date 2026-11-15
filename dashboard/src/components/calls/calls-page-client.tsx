"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeftRight,
  Phone,
  PhoneCall,
  PhoneMissed,
  RefreshCw,
  Search,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { readJsonResponse } from "@/lib/fetch-json";
import { cn } from "@/lib/utils";

type CallRow = {
  id: string;
  phone: string | null;
  duration_sec: number;
  outcome: string | null;
  disposition: string | null;
  transferred: boolean;
  sentiment: string | null;
  created_at: string;
  campaigns: { name: string } | null;
};

type TranscriptLine = { role: string; text: string };

type CallView = {
  id: string;
  createdAt: number;
  time: string;
  timeShort: string;
  campaign: string;
  phone: string;
  durationSec: number;
  duration: string;
  outcome: string;
  disposition: string;
  transferred: boolean;
  sentiment: string;
  transcript: TranscriptLine[];
  transcriptLoaded: boolean;
};

type FilterKey = "ALL" | "TODAY" | "7D" | "XFER" | "NO_XFER" | "OTHER";

const RAIL_KEY = "calls.railWidth";
const DETAIL_KEY = "calls.detailWidth";
const RAIL_MIN = 180;
const RAIL_MAX = 300;
const DETAIL_MIN = 320;
const DETAIL_MAX = 560;
const RAIL_DEFAULT = 220;
const DETAIL_DEFAULT = 400;

function formatDuration(sec: number): string {
  if (sec <= 0) return "—";
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function toView(row: CallRow): CallView {
  const created = new Date(row.created_at);
  return {
    id: row.id,
    createdAt: created.getTime(),
    time: created.toLocaleString(),
    timeShort: created.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    }),
    campaign: row.campaigns?.name ?? "—",
    phone: row.phone ?? "—",
    durationSec: row.duration_sec,
    duration: formatDuration(row.duration_sec),
    outcome: row.outcome ?? "—",
    disposition: row.disposition ?? "—",
    transferred: row.transferred,
    sentiment: row.sentiment ?? "—",
    transcript: [],
    transcriptLoaded: false,
  };
}

function outcomeMeta(outcome: string, transferred: boolean) {
  if (transferred) {
    return {
      label: "Transferred",
      code: "XFER",
      dot: "bg-brand",
      chip: "text-brand bg-brand-muted",
    };
  }
  const o = outcome.toUpperCase();
  if (o.includes("NI") || o.includes("NOT")) {
    return {
      label: "Not interested",
      code: outcome === "—" ? "NI" : outcome,
      dot: "bg-status-danger",
      chip: "text-status-danger bg-status-danger-muted",
    };
  }
  if (o.includes("DNC")) {
    return {
      label: "Do not call",
      code: "DNC",
      dot: "bg-status-danger",
      chip: "text-status-danger bg-status-danger-muted",
    };
  }
  if (o.includes("NA") || o.includes("NO ANSWER") || o.includes("BUSY")) {
    return {
      label: "No answer",
      code: outcome === "—" ? "NA" : outcome,
      dot: "bg-status-warning",
      chip: "text-status-warning bg-status-warning-muted",
    };
  }
  if (outcome === "—" || !outcome) {
    return {
      label: "Unknown",
      code: "—",
      dot: "bg-foreground-faint",
      chip: "text-foreground-muted bg-surface-overlay",
    };
  }
  return {
    label: outcome,
    code: outcome.slice(0, 8),
    dot: "bg-status-info",
    chip: "text-status-info bg-status-info-muted",
  };
}

function phoneInitials(phone: string) {
  const digits = phone.replace(/\D/g, "");
  return digits.slice(-2) || "?";
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

function startOfToday() {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

export function CallsPageClient() {
  const [allCalls, setAllCalls] = useState<CallView[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [loadingTranscript, setLoadingTranscript] = useState(false);
  const [error, setError] = useState("");
  const [hint, setHint] = useState("");
  const [filter, setFilter] = useState<FilterKey>("ALL");
  const [search, setSearch] = useState("");
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

  const sync = useCallback(async () => {
    setSyncing(true);
    setError("");
    try {
      const res = await fetch("/api/calls", { cache: "no-store" });
      const body = await readJsonResponse<{ calls?: CallRow[]; error?: string }>(res);
      if (!res.ok) throw new Error(body.error ?? "Failed to load calls");
      const rows = (body.calls ?? []).map(toView);
      setAllCalls(rows);
      setHint(`Synced — ${rows.length} call${rows.length === 1 ? "" : "s"}`);
      setSelectedId((prev) => {
        if (prev && rows.some((r) => r.id === prev)) return prev;
        return rows[0]?.id ?? null;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sync failed.");
      setAllCalls([]);
      setSelectedId(null);
    } finally {
      setSyncing(false);
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void sync();
  }, [sync]);

  const counts = useMemo(() => {
    const today = startOfToday();
    const week = Date.now() - 7 * 24 * 60 * 60 * 1000;
    let todayCount = 0;
    let weekCount = 0;
    let xfer = 0;
    let noXfer = 0;
    for (const c of allCalls) {
      if (c.createdAt >= today) todayCount += 1;
      if (c.createdAt >= week) weekCount += 1;
      if (c.transferred) xfer += 1;
      else noXfer += 1;
    }
    return {
      total: allCalls.length,
      today: todayCount,
      week: weekCount,
      xfer,
      noXfer,
    };
  }, [allCalls]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    const today = startOfToday();
    const week = Date.now() - 7 * 24 * 60 * 60 * 1000;
    return allCalls.filter((call) => {
      if (filter === "TODAY" && call.createdAt < today) return false;
      if (filter === "7D" && call.createdAt < week) return false;
      if (filter === "XFER" && !call.transferred) return false;
      if (filter === "NO_XFER" && call.transferred) return false;
      if (!q) return true;
      return (
        call.phone.toLowerCase().includes(q) ||
        call.campaign.toLowerCase().includes(q) ||
        call.outcome.toLowerCase().includes(q) ||
        call.disposition.toLowerCase().includes(q)
      );
    });
  }, [allCalls, filter, search]);

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

  const loadTranscript = useCallback(async (call: CallView) => {
    if (call.transcriptLoaded) return;
    setLoadingTranscript(true);
    setError("");
    try {
      const res = await fetch(`/api/calls/${call.id}`, { cache: "no-store" });
      const body = await readJsonResponse<{
        error?: string;
        call?: {
          transcript?: TranscriptLine[];
          sentiment?: string | null;
          disposition?: string | null;
        };
      }>(res);
      if (!res.ok) throw new Error(body.error ?? "Could not load transcript.");
      const patch: Partial<CallView> = {
        transcript: body.call?.transcript ?? [],
        transcriptLoaded: true,
        sentiment: body.call?.sentiment ?? call.sentiment,
        disposition: body.call?.disposition ?? call.disposition,
      };
      setAllCalls((prev) => prev.map((c) => (c.id === call.id ? { ...c, ...patch } : c)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load transcript.");
    } finally {
      setLoadingTranscript(false);
    }
  }, []);

  async function selectCall(call: CallView) {
    setSelectedId(call.id);
    await loadTranscript(call);
  }

  useEffect(() => {
    if (selected && !selected.transcriptLoaded) {
      void loadTranscript(selected);
    }
  }, [selected, loadTranscript]);

  const filterLabel =
    filter === "ALL"
      ? "All calls"
      : filter === "TODAY"
        ? "Today"
        : filter === "7D"
          ? "Last 7 days"
          : filter === "XFER"
            ? "Transferred"
            : "Not transferred";

  return (
    <div className="calls-shell relative flex h-full min-h-0 flex-1 flex-col overflow-hidden bg-surface-raised">
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
          className="calls-rail flex w-full shrink-0 flex-col border-b border-surface-border-subtle bg-surface/75 backdrop-blur-md lg:h-full lg:overflow-hidden lg:border-b-0 lg:border-r"
          style={{ ["--calls-rail" as string]: `${railWidth}px` }}
        >
          <div className="border-b border-surface-border-subtle px-4 py-4">
            <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-foreground-faint">
              Activity
            </p>
            <h1 className="mt-1 text-lg font-semibold tracking-tight text-foreground">Calls</h1>
            <p className="mt-1 truncate text-caption text-foreground-muted">
              {counts.total} logged
            </p>
          </div>

          <nav className="flex gap-1 overflow-x-auto p-2 scrollbar-thin lg:min-h-0 lg:flex-1 lg:flex-col lg:overflow-y-auto">
            <FilterChip
              active={filter === "ALL"}
              label="Everyone"
              count={counts.total}
              onClick={() => setFilter("ALL")}
              icon={<PhoneCall className="h-3.5 w-3.5 shrink-0 text-foreground-faint" />}
            />
            <FilterChip
              active={filter === "TODAY"}
              label="Today"
              count={counts.today}
              onClick={() => setFilter("TODAY")}
              dotClass="bg-status-success"
            />
            <FilterChip
              active={filter === "7D"}
              label="Last 7 days"
              count={counts.week}
              onClick={() => setFilter("7D")}
              dotClass="bg-status-info"
            />
            <FilterChip
              active={filter === "XFER"}
              label="Transferred"
              count={counts.xfer}
              onClick={() => setFilter("XFER")}
              dotClass="bg-brand"
            />
            <FilterChip
              active={filter === "NO_XFER"}
              label="Not transferred"
              count={counts.noXfer}
              onClick={() => setFilter("NO_XFER")}
              dotClass="bg-status-warning"
            />
          </nav>

          <div className="mt-auto hidden space-y-2 border-t border-surface-border-subtle p-3 lg:block">
            <MiniStat label="Today" value={counts.today} accent="text-status-success" />
            <MiniStat label="Transferred" value={counts.xfer} accent="text-brand" />
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
                placeholder="Search phone, campaign, outcome"
                className="h-10 border-transparent bg-surface-overlay pl-10 text-body placeholder:text-foreground-faint focus:border-brand/40"
              />
            </div>
            <Button variant="primary" size="sm" onClick={() => void sync()} disabled={syncing}>
              <RefreshCw className={cn("h-3.5 w-3.5", syncing && "animate-spin")} />
              {syncing ? "Syncing…" : "Sync"}
            </Button>
          </header>

          <div className="flex gap-2 overflow-x-auto border-b border-surface-border-subtle px-4 py-3 scrollbar-thin lg:hidden">
            <MiniStat label="Today" value={counts.today} accent="text-status-success" />
            <MiniStat label="Transferred" value={counts.xfer} accent="text-brand" />
            <MiniStat label="Total" value={counts.total} accent="text-foreground" />
          </div>

          {(error || hint) && (
            <div className="px-4 pt-3">
              {error ? (
                <p className="rounded-md border border-status-danger/30 bg-status-danger-muted px-3 py-2 text-caption text-status-danger">
                  {error}
                </p>
              ) : (
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
                <Phone className="h-3.5 w-3.5 text-foreground-faint" />
              </div>

              {loading ? (
                <div className="space-y-2 px-3 py-4">
                  {Array.from({ length: 7 }).map((_, i) => (
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
                    <PhoneMissed className="h-5 w-5 text-foreground-faint" />
                  </div>
                  <p className="text-body font-medium text-foreground-secondary">No calls here</p>
                  <p className="mt-1 max-w-xs text-caption text-foreground-faint">
                    Run a campaign and complete a call, then Sync to pull the log.
                  </p>
                </div>
              ) : (
                <ul className="space-y-0.5 px-2 pb-4 pt-1">
                  {filtered.map((call, index) => {
                    const meta = outcomeMeta(call.outcome, call.transferred);
                    const active = selected?.id === call.id;
                    return (
                      <li
                        key={call.id}
                        className="calls-row"
                        style={{ animationDelay: `${Math.min(index, 12) * 28}ms` }}
                      >
                        <button
                          type="button"
                          onClick={() => void selectCall(call)}
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
                                avatarTone(call.id),
                              )}
                            >
                              {phoneInitials(call.phone)}
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
                              <span className="truncate font-mono text-body font-medium text-foreground">
                                {call.phone}
                              </span>
                              <span
                                className={cn(
                                  "hidden shrink-0 rounded-sm px-1.5 py-0.5 text-2xs font-medium sm:inline",
                                  meta.chip,
                                )}
                              >
                                {meta.code}
                              </span>
                            </span>
                            <span className="mt-0.5 flex items-center gap-2 text-caption text-foreground-faint">
                              <span className="truncate">{call.timeShort}</span>
                              <span>·</span>
                              <span className="truncate">{call.duration}</span>
                              <span className="hidden sm:inline">·</span>
                              <span className="hidden truncate sm:inline">{call.campaign}</span>
                            </span>
                          </span>
                          {call.transferred && (
                            <ArrowLeftRight className="h-3.5 w-3.5 shrink-0 text-brand opacity-80" />
                          )}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>

            <ResizeHandle className="hidden lg:flex" onMouseDown={(e) => startResize("detail", e)} />

            <aside
              className="hidden shrink-0 border-t border-surface-border-subtle bg-surface/55 backdrop-blur-sm lg:flex lg:h-full lg:flex-col lg:overflow-hidden lg:border-l lg:border-t-0"
              style={{ width: detailWidth, minWidth: detailWidth }}
            >
              {selected ? (
                <CallDetail
                  call={selected}
                  loadingTranscript={loadingTranscript && !selected.transcriptLoaded}
                />
              ) : (
                <div className="flex h-full items-center justify-center p-6 text-center text-caption text-foreground-faint">
                  Select a call
                </div>
              )}
            </aside>
          </div>

          {selected && (
            <div className="max-h-[45vh] shrink-0 overflow-y-auto border-t border-surface-border-subtle bg-surface/70 scrollbar-thin lg:hidden">
              <CallDetail
                call={selected}
                loadingTranscript={loadingTranscript && !selected.transcriptLoaded}
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
      {dotClass ? (
        <span className={cn("h-2 w-2 shrink-0 rounded-full", dotClass)} />
      ) : (
        icon
      )}
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

function CallDetail({
  call,
  loadingTranscript,
  compact,
}: {
  call: CallView;
  loadingTranscript: boolean;
  compact?: boolean;
}) {
  const meta = outcomeMeta(call.outcome, call.transferred);
  return (
    <div className={cn("flex h-full min-h-0 flex-col", compact ? "p-4" : "p-5")}>
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "relative flex h-14 w-14 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br text-base font-semibold text-foreground ring-1 ring-white/5",
            avatarTone(call.id),
          )}
        >
          {phoneInitials(call.phone)}
          <span
            className={cn(
              "absolute bottom-0 right-0 h-3.5 w-3.5 rounded-full border-[3px] border-surface",
              meta.dot,
            )}
          />
        </span>
        <div className="min-w-0 pt-0.5">
          <p className="truncate font-mono text-base font-semibold text-foreground">{call.phone}</p>
          <p className="mt-0.5 truncate text-caption text-foreground-muted">{call.campaign}</p>
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

      <dl className="mt-5 grid grid-cols-2 gap-x-3 gap-y-3 border-t border-surface-border-subtle pt-4">
        <DetailRow label="When" value={call.time} />
        <DetailRow label="Duration" value={call.duration} />
        <DetailRow label="Outcome" value={call.outcome} />
        <DetailRow label="Disposition" value={call.disposition} mono />
        <DetailRow label="Transferred" value={call.transferred ? "Yes" : "No"} />
        <DetailRow label="Sentiment" value={call.sentiment} />
      </dl>

      <div className="mt-5 flex min-h-0 flex-1 flex-col border-t border-surface-border-subtle pt-4">
        <p className="mb-3 text-2xs font-semibold uppercase tracking-[0.12em] text-foreground-faint">
          Transcript
        </p>
        <div
          className={cn(
            "min-h-0 flex-1 space-y-3 overflow-y-auto rounded-md border border-surface-border-subtle bg-surface-overlay/80 p-3 scrollbar-thin",
            compact ? "max-h-48" : "",
          )}
        >
          {loadingTranscript ? (
            <p className="text-body text-foreground-faint">Loading transcript…</p>
          ) : call.transcript.length === 0 ? (
            <p className="text-body text-foreground-faint">
              No transcript for this call yet. New calls save one when the call ends.
            </p>
          ) : (
            call.transcript.map((line, i) => {
              const isBot = line.role === "bot" || line.role === "agent";
              return (
                <div
                  key={i}
                  className={cn(
                    "rounded-md px-3 py-2",
                    isBot ? "bg-brand-muted/40" : "bg-surface-raised/80",
                  )}
                >
                  <p className="text-2xs font-medium uppercase tracking-wide text-foreground-faint">
                    {isBot ? "Agent" : "Caller"}
                  </p>
                  <p className="mt-1 text-body leading-relaxed text-foreground-secondary">
                    {line.text}
                  </p>
                </div>
              );
            })
          )}
        </div>
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
    <div className="min-w-0">
      <dt className="text-caption text-foreground-faint">{label}</dt>
      <dd
        className={cn(
          "mt-0.5 truncate text-caption text-foreground-secondary",
          mono && "font-mono",
        )}
      >
        {value}
      </dd>
    </div>
  );
}
