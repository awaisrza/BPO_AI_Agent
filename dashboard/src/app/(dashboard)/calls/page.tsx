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
import { cn } from "@/lib/utils";

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
                    className={cn(
                      selected.id === call.id && "bg-white/[0.03]",
                    )}
                  >
                    <TableCell className="text-zinc-500">{call.time}</TableCell>
                    <TableCell className="text-zinc-500">{call.campaign}</TableCell>
                    <TableCell className="font-mono text-zinc-300">{call.phone}</TableCell>
                    <TableCell className="text-zinc-500">{call.duration}</TableCell>
                    <TableCell className="text-zinc-300">{call.outcome}</TableCell>
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
              <p className="mb-3 text-xs font-medium text-zinc-600">Transcript</p>
              <div className="max-h-72 space-y-4 overflow-y-auto rounded-lg bg-surface-overlay/50 p-4 scrollbar-thin">
                {selected.transcript.length === 0 ? (
                  <p className="text-sm text-zinc-600">No transcript — voicemail or short call</p>
                ) : (
                  selected.transcript.map((line, i) => (
                    <div key={i}>
                      <p className="text-2xs font-medium uppercase tracking-wide text-zinc-600">
                        {line.role === "bot" ? "Bot" : "Caller"}
                      </p>
                      <p className="mt-1 text-sm leading-relaxed text-zinc-300">{line.text}</p>
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
      <dt className="text-xs text-zinc-600">{label}</dt>
      <dd className={`mt-1 text-zinc-300 ${mono ? "font-mono text-sm" : ""}`}>{value}</dd>
    </div>
  );
}
