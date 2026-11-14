"use client";

import { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "@/components/ui/table";
import { readJsonResponse } from "@/lib/fetch-json";

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
  time: string;
  campaign: string;
  phone: string;
  duration: string;
  outcome: string;
  disposition: string;
  transferred: boolean;
  sentiment: string;
  transcript: TranscriptLine[];
  transcriptLoaded: boolean;
};

function formatDuration(sec: number): string {
  if (sec <= 0) return "—";
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function toView(row: CallRow): CallView {
  return {
    id: row.id,
    time: new Date(row.created_at).toLocaleString(),
    campaign: row.campaigns?.name ?? "—",
    phone: row.phone ?? "—",
    duration: formatDuration(row.duration_sec),
    outcome: row.outcome ?? "—",
    disposition: row.disposition ?? "—",
    transferred: row.transferred,
    sentiment: row.sentiment ?? "—",
    transcript: [],
    transcriptLoaded: false,
  };
}

export default function CallsPage() {
  const [calls, setCalls] = useState<CallView[]>([]);
  const [selected, setSelected] = useState<CallView | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [loadingTranscript, setLoadingTranscript] = useState(false);
  const [error, setError] = useState("");
  const [range, setRange] = useState("all");

  const sync = useCallback(async () => {
    setSyncing(true);
    setError("");
    try {
      const res = await fetch("/api/calls", { cache: "no-store" });
      const body = await readJsonResponse<{ calls?: CallRow[]; error?: string }>(res);
      if (!res.ok) throw new Error(body.error ?? "Failed to load calls");
      let raw = body.calls ?? [];
      if (range === "today") {
        const start = new Date();
        start.setHours(0, 0, 0, 0);
        raw = raw.filter((c) => new Date(c.created_at).getTime() >= start.getTime());
      } else if (range === "7d") {
        const start = Date.now() - 7 * 24 * 60 * 60 * 1000;
        raw = raw.filter((c) => new Date(c.created_at).getTime() >= start);
      }
      const rows = raw.map(toView);
      setCalls(rows);
      setSelected((prev) => {
        if (!prev) return rows[0] ?? null;
        return rows.find((r) => r.id === prev.id) ?? rows[0] ?? null;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sync failed.");
      setCalls([]);
      setSelected(null);
    } finally {
      setSyncing(false);
      setLoading(false);
    }
  }, [range]);

  useEffect(() => {
    void sync();
  }, [sync]);

  async function selectCall(call: CallView) {
    setSelected(call);
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
      const transcript = body.call?.transcript ?? [];
      const patch: Partial<CallView> = {
        transcript,
        transcriptLoaded: true,
        sentiment: body.call?.sentiment ?? call.sentiment,
        disposition: body.call?.disposition ?? call.disposition,
      };
      setCalls((prev) => prev.map((c) => (c.id === call.id ? { ...c, ...patch } : c)));
      setSelected((prev) => (prev?.id === call.id ? { ...prev, ...patch } : prev));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load transcript.");
    } finally {
      setLoadingTranscript(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Call log"
        description="Review every call, transcript, and disposition."
        action={
          <Button variant="secondary" onClick={() => void sync()} disabled={syncing}>
            <RefreshCw className={`h-4 w-4 ${syncing ? "animate-spin" : ""}`} />
            {syncing ? "Syncing…" : "Sync calls"}
          </Button>
        }
      />

      {error && (
        <p className="mb-6 rounded-lg border border-status-danger/30 bg-status-danger-muted px-4 py-3 text-sm text-status-danger">
          {error}
        </p>
      )}

      <div className="grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader
            title="Recent calls"
            action={
              <Select
                className="py-1.5 text-xs"
                value={range}
                onChange={(e) => setRange(e.target.value)}
              >
                <option value="today">Today</option>
                <option value="7d">Last 7 days</option>
                <option value="all">All calls</option>
              </Select>
            }
          />
          <CardBody className="px-0 pb-0 pt-0">
            {loading ? (
              <p className="px-4 py-6 text-body text-foreground-muted">Loading calls…</p>
            ) : calls.length === 0 ? (
              <p className="px-4 py-6 text-body text-foreground-muted">
                No calls yet — run a campaign and complete a call, then Sync.
              </p>
            ) : (
              <Table>
                <TableHead>
                  <TableHeaderCell>Time</TableHeaderCell>
                  <TableHeaderCell>Campaign</TableHeaderCell>
                  <TableHeaderCell>Lead</TableHeaderCell>
                  <TableHeaderCell>Duration</TableHeaderCell>
                  <TableHeaderCell>Outcome</TableHeaderCell>
                  <TableHeaderCell>Transfer</TableHeaderCell>
                </TableHead>
                <TableBody>
                  {calls.map((call) => (
                    <TableRow
                      key={call.id}
                      onClick={() => void selectCall(call)}
                      selected={selected?.id === call.id}
                    >
                      <TableCell className="text-foreground-muted">{call.time}</TableCell>
                      <TableCell className="text-foreground-muted">{call.campaign}</TableCell>
                      <TableCell className="font-mono text-caption text-foreground-secondary">
                        {call.phone}
                      </TableCell>
                      <TableCell className="text-foreground-muted">{call.duration}</TableCell>
                      <TableCell className="text-foreground-secondary">{call.outcome}</TableCell>
                      <TableCell>
                        <Badge variant={call.transferred ? "success" : "default"}>
                          {call.transferred ? "Yes" : "No"}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardBody>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader title="Call detail" />
          <CardBody className="space-y-6">
            {selected ? (
              <>
                <dl className="grid grid-cols-2 gap-4 text-sm">
                  <DetailItem label="Lead" value={selected.phone} mono />
                  <DetailItem label="Disposition" value={selected.disposition} mono />
                  <DetailItem label="Outcome" value={selected.outcome} />
                  <DetailItem
                    label="Transferred"
                    value={selected.transferred ? "Yes" : "No"}
                  />
                </dl>

                <div>
                  <p className="data-label mb-3">Transcript</p>
                  <div className="max-h-72 space-y-3 overflow-y-auto rounded-md border border-surface-border-subtle bg-surface-overlay p-4 scrollbar-thin">
                    {loadingTranscript && !selected.transcriptLoaded ? (
                      <p className="text-body text-foreground-faint">Loading transcript…</p>
                    ) : selected.transcript.length === 0 ? (
                      <p className="text-body text-foreground-faint">
                        No transcript for this call yet. New calls after the GPU update will
                        save one when the call ends.
                      </p>
                    ) : (
                      selected.transcript.map((line, i) => (
                        <div key={i}>
                          <p className="text-2xs font-medium uppercase tracking-wide text-foreground-faint">
                            {line.role === "bot" ? "Agent" : "Caller"}
                          </p>
                          <p className="mt-1 text-body leading-relaxed text-foreground-secondary">
                            {line.text}
                          </p>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </>
            ) : (
              <p className="text-body text-foreground-muted">Select a call to view details.</p>
            )}
          </CardBody>
        </Card>
      </div>
    </>
  );
}

function DetailItem({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <dt className="data-label">{label}</dt>
      <dd
        className={`mt-1 text-body text-foreground-secondary ${mono ? "font-mono text-caption" : ""}`}
      >
        {value}
      </dd>
    </div>
  );
}
