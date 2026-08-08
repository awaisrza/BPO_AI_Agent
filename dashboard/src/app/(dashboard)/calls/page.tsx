"use client";

import { useEffect, useState } from "react";
import { FileText, Play } from "lucide-react";
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

type CallRow = {
  id: string;
  phone: string | null;
  duration_sec: number;
  outcome: string | null;
  disposition: string | null;
  transferred: boolean;
  created_at: string;
  campaigns: { name: string } | null;
};

type CallView = {
  id: string;
  time: string;
  campaign: string;
  phone: string;
  duration: string;
  outcome: string;
  disposition: string;
  transferred: boolean;
  queue: string;
  sentiment: string;
  transcript: { role: string; text: string }[];
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
    queue: "—",
    sentiment: "—",
    transcript: [],
  };
}

export default function CallsPage() {
  const [calls, setCalls] = useState<CallView[]>([]);
  const [selected, setSelected] = useState<CallView | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/calls", { cache: "no-store" });
        const body = (await res.json()) as { calls?: CallRow[]; error?: string };
        if (!res.ok) throw new Error(body.error ?? "Failed to load calls");
        const rows = (body.calls ?? []).map(toView);
        if (!cancelled) {
          setCalls(rows);
          setSelected(rows[0] ?? null);
        }
      } catch {
        if (!cancelled) {
          setCalls([]);
          setSelected(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
      <PageHeader
        title="Call log"
        description="Review every call, transcript, and disposition."
      />

      <div className="grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader
            title="Recent calls"
            action={
              <Select className="py-1.5 text-xs">
                <option>Today</option>
                <option>Last 7 days</option>
                <option>All campaigns</option>
              </Select>
            }
          />
          <CardBody className="px-0 pb-0 pt-0">
            {loading ? (
              <p className="px-4 py-6 text-body text-foreground-muted">Loading calls…</p>
            ) : calls.length === 0 ? (
              <p className="px-4 py-6 text-body text-foreground-muted">
                No calls yet — run a campaign and complete a test dial.
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
                      onClick={() => setSelected(call)}
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
          <CardHeader
            title="Call detail"
            action={
              <div className="flex gap-1">
                <Button variant="ghost" size="sm" className="!px-2">
                  <Play className="h-4 w-4" />
                </Button>
                <Button variant="ghost" size="sm" className="!px-2">
                  <FileText className="h-4 w-4" />
                </Button>
              </div>
            }
          />
          <CardBody className="space-y-6">
            {selected ? (
              <>
                <dl className="grid grid-cols-2 gap-4 text-sm">
                  <DetailItem label="Disposition" value={selected.disposition} mono />
                  <DetailItem label="Queue" value={selected.queue} mono />
                  <DetailItem label="Sentiment" value={selected.sentiment} />
                  <DetailItem
                    label="Transferred"
                    value={selected.transferred ? "Yes" : "No"}
                  />
                </dl>

                <div>
                  <p className="data-label mb-3">Transcript</p>
                  <div className="max-h-72 space-y-3 overflow-y-auto rounded-md border border-surface-border-subtle bg-surface-overlay p-4 scrollbar-thin">
                    {selected.transcript.length === 0 ? (
                      <p className="text-body text-foreground-faint">
                        No transcript captured yet for this call.
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
