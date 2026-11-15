"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Download, Phone, RefreshCw, RotateCcw, Search, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { readJsonResponse } from "@/lib/fetch-json";
import { cn } from "@/lib/utils";
import type { VicidialLead, VicidialLeadSummary } from "@/lib/vicidial/leads";

const emptySummary: VicidialLeadSummary = {
  total: 0,
  new: 0,
  dialed: 0,
  transferred: 0,
  notInterested: 0,
  dnc: 0,
};

const RAIL_KEY = "leads.railWidth";
const DETAIL_KEY = "leads.detailWidth";
const RAIL_MIN = 180;
const RAIL_MAX = 320;
const DETAIL_MIN = 240;
const DETAIL_MAX = 420;
const RAIL_DEFAULT = 224;
const DETAIL_DEFAULT = 300;

const STATUS_META: Record<
  string,
  { label: string; dot: string; chip: string; hint: string }
> = {
  NEW: {
    label: "Dialable",
    dot: "bg-status-success",
    chip: "text-status-success bg-status-success-muted",
    hint: "Ready for Run campaign",
  },
  CALLBK: {
    label: "Callback",
    dot: "bg-status-info",
    chip: "text-status-info bg-status-info-muted",
    hint: "Scheduled callback",
  },
  XFER: {
    label: "Transferred",
    dot: "bg-brand",
    chip: "text-brand bg-brand-muted",
    hint: "Handed to closer",
  },
  NI: {
    label: "Not interested",
    dot: "bg-status-danger",
    chip: "text-status-danger bg-status-danger-muted",
    hint: "Declined",
  },
  DNC: {
    label: "Do not call",
    dot: "bg-status-danger",
    chip: "text-status-danger bg-status-danger-muted",
    hint: "Blocked",
  },
  NA: {
    label: "No answer",
    dot: "bg-status-warning",
    chip: "text-status-warning bg-status-warning-muted",
    hint: "No connect",
  },
  AB: {
    label: "Abandoned",
    dot: "bg-status-warning",
    chip: "text-status-warning bg-status-warning-muted",
    hint: "Dropped early",
  },
  DROP: {
    label: "Dropped",
    dot: "bg-status-warning",
    chip: "text-status-warning bg-status-warning-muted",
    hint: "Dropped",
  },
  SKIP: {
    label: "Skipped",
    dot: "bg-foreground-faint",
    chip: "text-foreground-muted bg-surface-overlay",
    hint: "Not dialed",
  },
};

function statusMeta(status: string) {
  return (
    STATUS_META[status.toUpperCase()] ?? {
      label: status,
      dot: "bg-foreground-faint",
      chip: "text-foreground-muted bg-surface-overlay",
      hint: status,
    }
  );
}

function initials(name: string, phone: string) {
  const parts = name.replace(/[—-]/g, " ").trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2 && parts[0] !== "—") {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  if (parts[0] && parts[0] !== "—") return parts[0].slice(0, 2).toUpperCase();
  const digits = phone.replace(/\D/g, "");
  return digits.slice(-2) || "?";
}

function avatarTone(leadId: number) {
  const tones = [
    "from-sky-600/40 to-sky-900/50",
    "from-teal-600/40 to-teal-900/50",
    "from-amber-600/35 to-amber-900/50",
    "from-rose-600/35 to-rose-900/50",
    "from-indigo-600/40 to-indigo-900/50",
  ];
  return tones[Math.abs(leadId) % tones.length];
}

function readStoredWidth(key: string, fallback: number, min: number, max: number) {
  if (typeof window === "undefined") return fallback;
  const raw = Number(window.localStorage.getItem(key));
  if (!Number.isFinite(raw)) return fallback;
  return Math.min(max, Math.max(min, raw));
}

export function LeadsPageClient() {
  const [leads, setLeads] = useState<VicidialLead[]>([]);
  const [summary, setSummary] = useState<VicidialLeadSummary>(emptySummary);
  const [campaignId, setCampaignId] = useState("test_cam");
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState("");
  const [hint, setHint] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [resettingId, setResettingId] = useState<number | null>(null);
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
      const res = await fetch(
        `/api/vicidial/leads?campaign_id=${encodeURIComponent(campaignId)}`,
        { cache: "no-store" },
      );
      const data = await readJsonResponse<{
        error?: string;
        leads?: VicidialLead[];
        summary?: VicidialLeadSummary;
        campaignId?: string;
        detail?: string;
      }>(res);
      if (!res.ok) throw new Error(data.error ?? "Could not sync leads from ViciDial.");
      const next = data.leads ?? [];
      setLeads(next);
      setSummary(data.summary ?? emptySummary);
      if (data.campaignId) setCampaignId(data.campaignId);
      setHint(data.detail ? `Synced — ${data.detail}` : "Live from ViciDial.");
      setSelectedId((prev) => {
        if (prev && next.some((l) => l.leadId === prev)) return prev;
        return next[0]?.leadId ?? null;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sync failed.");
    } finally {
      setSyncing(false);
      setLoading(false);
    }
  }, [campaignId]);

  useEffect(() => {
    void sync();
  }, [sync]);

  async function resetToNew(lead: VicidialLead) {
    setError("");
    setResettingId(lead.leadId);
    try {
      const res = await fetch("/api/vicidial/leads", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          phone: lead.phone,
          campaign_id: campaignId,
          list_id: String(lead.listId),
          status: "NEW",
          first_name: lead.firstName,
          last_name: lead.lastName,
        }),
      });
      const data = await readJsonResponse<{
        error?: string;
        message?: string;
        leads?: VicidialLead[];
        summary?: VicidialLeadSummary;
      }>(res);
      if (!res.ok) throw new Error(data.error ?? "Could not reset lead.");
      setLeads(data.leads ?? []);
      setSummary(data.summary ?? emptySummary);
      setHint(data.message ?? `Reset ${lead.phone} to NEW.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reset lead.");
    } finally {
      setResettingId(null);
    }
  }

  const statusCounts = useMemo(() => {
    const map = new Map<string, number>();
    for (const lead of leads) {
      map.set(lead.status, (map.get(lead.status) ?? 0) + 1);
    }
    return map;
  }, [leads]);

  const statuses = useMemo(() => {
    return ["ALL", ...Array.from(statusCounts.keys()).sort()];
  }, [statusCounts]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return leads.filter((lead) => {
      if (statusFilter !== "ALL" && lead.status !== statusFilter) return false;
      if (!q) return true;
      return (
        lead.phone.toLowerCase().includes(q) ||
        lead.phoneNumber.includes(q) ||
        lead.name.toLowerCase().includes(q)
      );
    });
  }, [leads, search, statusFilter]);

  const selected = useMemo(
    () => filtered.find((l) => l.leadId === selectedId) ?? filtered[0] ?? null,
    [filtered, selectedId],
  );

  function exportExcel() {
    const rows = filtered.length ? filtered : leads;
    if (!rows.length) {
      setError("Nothing to export — sync leads first.");
      return;
    }
    const escapeXml = (v: string) =>
      v
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    const cell = (v: string | number, type: "String" | "Number" = "String") =>
      `<Cell><Data ss:Type="${type}">${escapeXml(String(v ?? ""))}</Data></Cell>`;
    const header = ["Lead ID", "Phone", "Name", "Status", "List", "Calls", "Last attempt"]
      .map((h) => cell(h))
      .join("");
    const body = rows
      .map(
        (lead) =>
          `<Row>${cell(lead.leadId, "Number")}${cell(lead.phone)}${cell(lead.name)}${cell(lead.status)}${cell(lead.listId, "Number")}${cell(lead.calledCount, "Number")}${cell(lead.lastAttempt || "")}</Row>`,
      )
      .join("");
    const xml = `<?xml version="1.0"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Worksheet ss:Name="Leads">
  <Table>
   <Row>${header}</Row>
   ${body}
  </Table>
 </Worksheet>
</Workbook>`;
    const blob = new Blob([xml], { type: "application/vnd.ms-excel" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const stamp = new Date().toISOString().slice(0, 10);
    a.href = url;
    a.download = `leads-${campaignId}-${stamp}.xls`;
    a.click();
    URL.revokeObjectURL(url);
    setHint(`Exported ${rows.length} lead(s) to Excel.`);
  }

  return (
    <div
      className="leads-shell relative -mx-4 -my-6 flex h-[calc(100dvh-3.5rem)] flex-col overflow-hidden border-y border-surface-border bg-surface-raised sm:-mx-6 lg:-mx-8 lg:-my-8 lg:h-[calc(100dvh-3.5rem)] lg:rounded-none"
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_80%_50%_at_0%_0%,rgba(59,130,246,0.12),transparent_55%),radial-gradient(ellipse_60%_40%_at_100%_100%,rgba(15,23,42,0.85),transparent_55%)]"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.28] [background-image:linear-gradient(rgba(255,255,255,0.028)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.028)_1px,transparent_1px)] [background-size:40px_40px] [mask-image:radial-gradient(ellipse_at_center,black_40%,transparent_85%)]"
      />

      <div className="relative flex min-h-0 flex-1 flex-col lg:flex-row">
        {/* Status rail */}
        <aside
          className="leads-rail flex w-full shrink-0 flex-col border-b border-surface-border-subtle bg-surface/75 backdrop-blur-md lg:h-full lg:overflow-hidden lg:border-b-0 lg:border-r"
          style={{ ["--leads-rail" as string]: `${railWidth}px` }}
        >
          <div className="border-b border-surface-border-subtle px-4 py-4">
            <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-foreground-faint">
              Directory
            </p>
            <h1 className="mt-1 text-lg font-semibold tracking-tight text-foreground">Leads</h1>
            <p className="mt-1 truncate text-caption text-foreground-muted">{campaignId}</p>
          </div>

          <nav className="flex gap-1 overflow-x-auto p-2 scrollbar-thin lg:min-h-0 lg:flex-1 lg:flex-col lg:overflow-y-auto">
            <FilterChip
              active={statusFilter === "ALL"}
              label="Everyone"
              count={summary.total}
              onClick={() => setStatusFilter("ALL")}
            />
            {statuses
              .filter((s) => s !== "ALL")
              .map((s) => {
                const meta = statusMeta(s);
                return (
                  <FilterChip
                    key={s}
                    active={statusFilter === s}
                    label={meta.label}
                    count={statusCounts.get(s) ?? 0}
                    dotClass={meta.dot}
                    onClick={() => setStatusFilter(s)}
                  />
                );
              })}
          </nav>

          <div className="mt-auto hidden space-y-2 border-t border-surface-border-subtle p-3 lg:block">
            <MiniStat label="Dialable" value={summary.new} accent="text-status-success" />
            <MiniStat label="Transferred" value={summary.transferred} accent="text-brand" />
            <MiniStat label="DNC" value={summary.dnc} accent="text-status-danger" />
          </div>
        </aside>

        <ResizeHandle className="hidden lg:flex" onMouseDown={(e) => startResize("rail", e)} />

        {/* Main list */}
        <section className="flex min-h-0 min-w-0 flex-1 flex-col">
          <header className="flex flex-col gap-3 border-b border-surface-border-subtle bg-surface-raised/80 px-4 py-3 backdrop-blur-md sm:flex-row sm:items-center sm:justify-between">
            <div className="relative min-w-0 flex-1 sm:max-w-md">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-foreground-faint" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search phone or name"
                className="h-10 border-transparent bg-surface-overlay pl-10 text-body placeholder:text-foreground-faint focus:border-brand/40"
              />
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={exportExcel}
                disabled={loading || (!filtered.length && !leads.length)}
              >
                <Download className="h-3.5 w-3.5" />
                Export
              </Button>
              <Button variant="primary" size="sm" onClick={() => void sync()} disabled={syncing}>
                <RefreshCw className={cn("h-3.5 w-3.5", syncing && "animate-spin")} />
                {syncing ? "Syncing…" : "Sync"}
              </Button>
            </div>
          </header>

          <div className="flex gap-2 overflow-x-auto border-b border-surface-border-subtle px-4 py-3 scrollbar-thin lg:hidden">
            <MiniStat label="Dialable" value={summary.new} accent="text-status-success" />
            <MiniStat label="Transferred" value={summary.transferred} accent="text-brand" />
            <MiniStat label="DNC" value={summary.dnc} accent="text-status-danger" />
            <MiniStat label="Total" value={summary.total} accent="text-foreground" />
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
                  {statusFilter === "ALL" ? "All leads" : statusMeta(statusFilter).label}
                  <span className="ml-2 font-medium text-foreground-muted">— {filtered.length}</span>
                </p>
                <Users className="h-3.5 w-3.5 text-foreground-faint" />
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
                    <Phone className="h-5 w-5 text-foreground-faint" />
                  </div>
                  <p className="text-body font-medium text-foreground-secondary">No leads here</p>
                  <p className="mt-1 max-w-xs text-caption text-foreground-faint">
                    Sync ViciDial or reset a finished lead to NEW so Run campaign can dial it.
                  </p>
                </div>
              ) : (
                <ul className="space-y-0.5 px-2 pb-4 pt-1">
                  {filtered.map((lead, index) => {
                    const meta = statusMeta(lead.status);
                    const active = selected?.leadId === lead.leadId;
                    return (
                      <li
                        key={lead.leadId}
                        className="leads-row"
                        style={{ animationDelay: `${Math.min(index, 12) * 28}ms` }}
                      >
                        <button
                          type="button"
                          onClick={() => setSelectedId(lead.leadId)}
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
                                avatarTone(lead.leadId),
                              )}
                            >
                              {initials(lead.name, lead.phone)}
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
                                {lead.name !== "—" ? lead.name : lead.phone}
                              </span>
                              <span
                                className={cn(
                                  "hidden shrink-0 rounded-sm px-1.5 py-0.5 text-2xs font-medium sm:inline",
                                  meta.chip,
                                )}
                              >
                                {lead.status}
                              </span>
                            </span>
                            <span className="mt-0.5 flex items-center gap-2 text-caption text-foreground-faint">
                              <span className="truncate font-mono">{lead.phone}</span>
                              <span className="hidden sm:inline">·</span>
                              <span className="hidden truncate sm:inline">
                                {lead.calledCount} call{lead.calledCount === 1 ? "" : "s"}
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

            {/* Detail pane */}
            <aside
              className="hidden shrink-0 border-t border-surface-border-subtle bg-surface/55 backdrop-blur-sm lg:block lg:h-full lg:overflow-y-auto lg:border-l lg:border-t-0"
              style={{ width: detailWidth, minWidth: detailWidth }}
            >
              {selected ? (
                <LeadDetail
                  lead={selected}
                  resetting={resettingId === selected.leadId}
                  onReset={() => void resetToNew(selected)}
                />
              ) : (
                <div className="flex h-full items-center justify-center p-6 text-center text-caption text-foreground-faint">
                  Select a lead
                </div>
              )}
            </aside>
          </div>

          {selected && (
            <div className="shrink-0 border-t border-surface-border-subtle bg-surface/70 lg:hidden">
              <LeadDetail
                lead={selected}
                resetting={resettingId === selected.leadId}
                onReset={() => void resetToNew(selected)}
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
  onClick,
}: {
  active: boolean;
  label: string;
  count: number;
  dotClass?: string;
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
        <Users className="h-3.5 w-3.5 shrink-0 text-foreground-faint" />
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

function LeadDetail({
  lead,
  resetting,
  onReset,
  compact,
}: {
  lead: VicidialLead;
  resetting: boolean;
  onReset: () => void;
  compact?: boolean;
}) {
  const meta = statusMeta(lead.status);
  return (
    <div className={cn("flex h-full flex-col", compact ? "p-4" : "p-5")}>
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "relative flex h-14 w-14 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br text-base font-semibold text-foreground ring-1 ring-white/5",
            avatarTone(lead.leadId),
          )}
        >
          {initials(lead.name, lead.phone)}
          <span
            className={cn(
              "absolute bottom-0 right-0 h-3.5 w-3.5 rounded-full border-[3px] border-surface",
              meta.dot,
            )}
          />
        </span>
        <div className="min-w-0 pt-0.5">
          <p className="truncate text-base font-semibold text-foreground">
            {lead.name !== "—" ? lead.name : "Unknown"}
          </p>
          <p className="mt-0.5 font-mono text-caption text-foreground-muted">{lead.phone}</p>
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

      <dl className="mt-5 space-y-3 border-t border-surface-border-subtle pt-4">
        <DetailRow label="Lead ID" value={String(lead.leadId)} mono />
        <DetailRow label="List" value={String(lead.listId)} />
        <DetailRow label="Calls" value={String(lead.calledCount)} />
        <DetailRow label="Last attempt" value={lead.lastAttempt || "—"} />
        <DetailRow label="Status" value={meta.hint} />
      </dl>

      <div className="mt-auto pt-5">
        {lead.status !== "NEW" ? (
          <Button className="w-full" onClick={onReset} disabled={resetting}>
            <RotateCcw className={cn("h-4 w-4", resetting && "animate-spin")} />
            {resetting ? "Resetting…" : "Reset to NEW"}
          </Button>
        ) : (
          <p className="rounded-md border border-status-success/20 bg-status-success-muted px-3 py-2.5 text-center text-caption text-status-success">
            Dialable — ready for Run campaign
          </p>
        )}
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
