"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Download, RefreshCw, Search } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { StatCard } from "@/components/ui/stat-card";
import { Input, Select } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "@/components/ui/table";
import { readJsonResponse } from "@/lib/fetch-json";
import type { VicidialLead, VicidialLeadSummary } from "@/lib/vicidial/leads";

function leadStatusBadge(status: string) {
  const s = status.toUpperCase();
  const map: Record<string, "default" | "info" | "success" | "warning" | "danger"> = {
    NEW: "default",
    CALLBK: "info",
    XFER: "success",
    NI: "danger",
    DNC: "danger",
    NA: "warning",
    AB: "warning",
    DROP: "warning",
    SKIP: "default",
  };
  return <Badge variant={map[s] ?? "info"}>{s}</Badge>;
}

const emptySummary: VicidialLeadSummary = {
  total: 0,
  new: 0,
  dialed: 0,
  transferred: 0,
  notInterested: 0,
  dnc: 0,
};

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
      setLeads(data.leads ?? []);
      setSummary(data.summary ?? emptySummary);
      if (data.campaignId) setCampaignId(data.campaignId);
      setHint(data.detail ? `Synced — ${data.detail}` : "Synced from ViciDial.");
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
    }
  }

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

  const statuses = useMemo(() => {
    const set = new Set(leads.map((l) => l.status));
    return ["ALL", ...Array.from(set).sort()];
  }, [leads]);

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
    <>
      <PageHeader
        title="Leads"
        description={`ViciDial list for campaign ${campaignId}. Sync pulls live dialer rows.`}
        action={
          <>
            <Button
              variant="secondary"
              onClick={exportExcel}
              disabled={loading || (!filtered.length && !leads.length)}
            >
              <Download className="h-4 w-4" />
              Export Excel
            </Button>
            <Button variant="secondary" onClick={() => void sync()} disabled={syncing}>
              <RefreshCw className={`h-4 w-4 ${syncing ? "animate-spin" : ""}`} />
              {syncing ? "Syncing…" : "Sync ViciDial"}
            </Button>
          </>
        }
      />

      {error && (
        <p className="mb-6 rounded-lg border border-status-danger/30 bg-status-danger-muted px-4 py-3 text-sm text-status-danger">
          {error}
        </p>
      )}
      {hint && !error && (
        <p className="mb-6 rounded-lg border border-border bg-surface-raised px-4 py-3 text-sm text-foreground-muted">
          {hint}
        </p>
      )}

      <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <StatCard label="Total" value={summary.total.toLocaleString()} />
        <StatCard label="NEW (dialable)" value={summary.new.toLocaleString()} />
        <StatCard label="Dialed" value={summary.dialed.toLocaleString()} />
        <StatCard label="Transferred" value={summary.transferred.toLocaleString()} />
        <StatCard label="DNC" value={summary.dnc.toLocaleString()} />
      </div>

      <Card>
        <CardHeader
          title="Dialer leads"
          action={
            <div className="flex items-center gap-2">
              <Select
                className="py-1.5 text-xs"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
              >
                {statuses.map((s) => (
                  <option key={s} value={s}>
                    {s === "ALL" ? "All statuses" : s}
                  </option>
                ))}
              </Select>
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-zinc-600" />
                <Input
                  placeholder="Search phone..."
                  className="w-44 py-1.5 pl-8 text-xs"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>
            </div>
          }
        />
        <CardBody className="px-0 pb-0 pt-0">
          {loading ? (
            <p className="px-6 py-8 text-sm text-foreground-muted">Loading leads from ViciDial…</p>
          ) : (
            <Table>
              <TableHead>
                <TableHeaderCell>Phone</TableHeaderCell>
                <TableHeaderCell>Name</TableHeaderCell>
                <TableHeaderCell>Status</TableHeaderCell>
                <TableHeaderCell>List</TableHeaderCell>
                <TableHeaderCell>Last attempt</TableHeaderCell>
                <TableHeaderCell>Calls</TableHeaderCell>
                <TableHeaderCell>Action</TableHeaderCell>
              </TableHead>
              <TableBody>
                {filtered.length === 0 ? (
                  <TableRow>
                    <TableCell className="text-foreground-muted" colSpan={7}>
                      No leads match. Sync ViciDial or add a number above.
                    </TableCell>
                  </TableRow>
                ) : (
                  filtered.map((lead) => (
                    <TableRow key={lead.leadId}>
                      <TableCell className="font-mono text-zinc-300">{lead.phone}</TableCell>
                      <TableCell className="text-zinc-500">{lead.name}</TableCell>
                      <TableCell>{leadStatusBadge(lead.status)}</TableCell>
                      <TableCell className="text-zinc-500">{lead.listId}</TableCell>
                      <TableCell className="text-zinc-600">{lead.lastAttempt || "—"}</TableCell>
                      <TableCell className="text-zinc-500">{lead.calledCount}</TableCell>
                      <TableCell>
                        {lead.status !== "NEW" ? (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => void resetToNew(lead)}
                          >
                            Reset to NEW
                          </Button>
                        ) : (
                          <span className="text-xs text-foreground-faint">Dialable</span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          )}
        </CardBody>
      </Card>
    </>
  );
}
