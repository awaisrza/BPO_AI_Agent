"use client";

import { useState } from "react";
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
import { calls } from "@/lib/mock-data";

export default function CallsPage() {
  const [selected, setSelected] = useState(calls[0]);

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
                <option>Medicare AEP</option>
              </Select>
            }
          />
          <CardBody className="px-0 pb-0 pt-0">
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
                    selected={selected.id === call.id}
                  >
                    <TableCell className="text-foreground-muted">{call.time}</TableCell>
                    <TableCell className="text-foreground-muted">{call.campaign}</TableCell>
                    <TableCell className="font-mono text-caption text-foreground-secondary">{call.phone}</TableCell>
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
            <dl className="grid grid-cols-2 gap-4 text-sm">
              <DetailItem label="Disposition" value={selected.disposition} mono />
              <DetailItem label="Queue" value={selected.queue} mono />
              <DetailItem label="Sentiment" value={selected.sentiment} />
              <DetailItem label="Transferred" value={selected.transferred ? "Yes" : "No"} />
            </dl>

            <div>
              <p className="data-label mb-3">Transcript</p>
              <div className="max-h-72 space-y-3 overflow-y-auto rounded-md border border-surface-border-subtle bg-surface-overlay p-4 scrollbar-thin">
                {selected.transcript.length === 0 ? (
                  <p className="text-body text-foreground-faint">No transcript — voicemail or short call</p>
                ) : (
                  selected.transcript.map((line, i) => (
                    <div key={i}>
                      <p className="text-2xs font-medium uppercase tracking-wide text-foreground-faint">
                        {line.role === "bot" ? "Agent" : "Caller"}
                      </p>
                      <p className="mt-1 text-body leading-relaxed text-foreground-secondary">{line.text}</p>
                    </div>
                  ))
                )}
              </div>
            </div>
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
      <dd className={`mt-1 text-body text-foreground-secondary ${mono ? "font-mono text-caption" : ""}`}>{value}</dd>
    </div>
  );
}
