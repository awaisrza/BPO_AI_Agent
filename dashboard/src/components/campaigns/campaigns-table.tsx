"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "@/components/ui/table";
import { campaigns as mockCampaigns } from "@/lib/mock-data";
import { getStoredCampaigns, type Campaign } from "@/lib/campaigns";

export function CampaignsTable() {
  const [campaigns, setCampaigns] = useState<Campaign[]>(mockCampaigns);

  useEffect(() => {
    function refresh() {
      const mockIds = new Set(mockCampaigns.map((c) => c.id));
      const stored = getStoredCampaigns().filter((c) => !mockIds.has(c.id));
      setCampaigns([...mockCampaigns, ...stored]);
    }

    refresh();
    window.addEventListener("campaigns-updated", refresh);
    return () => window.removeEventListener("campaigns-updated", refresh);
  }, []);

  return (
    <Card>
      <CardHeader title="Active campaigns" />
      <CardBody className="px-0 pb-0 pt-0">
        <Table>
          <TableHead>
            <TableHeaderCell>Campaign</TableHeaderCell>
            <TableHeaderCell>Script</TableHeaderCell>
            <TableHeaderCell>Bots</TableHeaderCell>
            <TableHeaderCell>Status</TableHeaderCell>
            <TableHeaderCell className="text-right">Dials</TableHeaderCell>
            <TableHeaderCell className="text-right">Transfer</TableHeaderCell>
            <TableHeaderCell>{" "}</TableHeaderCell>
          </TableHead>
          <TableBody>
            {campaigns.map((c) => (
              <TableRow key={c.id}>
                <TableCell className="font-medium text-zinc-200">{c.name}</TableCell>
                <TableCell className="text-zinc-500">{c.script}</TableCell>
                <TableCell className="text-zinc-500">{c.bots}</TableCell>
                <TableCell>
                  <Badge
                    variant={c.status === "running" ? "live" : "default"}
                    dot={c.status === "running"}
                  >
                    {c.status === "running" ? "Running" : "Paused"}
                  </Badge>
                </TableCell>
                <TableCell className="text-right tabular-nums text-zinc-500">
                  {c.dials.toLocaleString()}
                </TableCell>
                <TableCell className="text-right tabular-nums text-zinc-300">
                  {c.transferRate ? `${c.transferRate}%` : "—"}
                </TableCell>
                <TableCell className="text-right">
                  <Link
                    href={`/campaigns/${c.id}`}
                    className="text-sm text-zinc-400 transition-colors hover:text-zinc-200"
                  >
                    Edit
                  </Link>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardBody>
    </Card>
  );
}
