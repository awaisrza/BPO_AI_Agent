"use client";

import { useCallback, useEffect, useState } from "react";
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
import { createClient, isSupabaseConfigured } from "@/lib/supabase/client";
import { toListItem, type CampaignListItem } from "@/lib/campaigns";
import { formatSupabaseError } from "@/lib/errors";
import type { CampaignRow } from "@/lib/types/database";

export function CampaignsTable() {
  const [campaigns, setCampaigns] = useState<CampaignListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadCampaigns = useCallback(async () => {
    if (!isSupabaseConfigured()) {
      setError("Add Supabase keys to .env.local and restart the dev server.");
      setLoading(false);
      return;
    }

    setLoading(true);
    setError("");

    try {
      const supabase = createClient();
      const { data: rows, error: campaignsError } = await supabase
        .from("campaigns")
        .select("id, name, status, script_json")
        .order("name", { ascending: true });

      if (campaignsError) throw campaignsError;

      let botCounts: Record<string, number> = {};
      const { data: bots, error: botsError } = await supabase
        .from("bots")
        .select("campaign_id");

      if (!botsError) {
        botCounts = (bots ?? []).reduce<Record<string, number>>((acc, bot) => {
        if (bot.campaign_id) {
          acc[bot.campaign_id] = (acc[bot.campaign_id] ?? 0) + 1;
        }
          return acc;
        }, {});
      }

      setCampaigns(
        ((rows ?? []) as CampaignRow[]).map((row) =>
          toListItem(row, botCounts[row.id] ?? 0),
        ),
      );
    } catch (err) {
      setError(formatSupabaseError(err, "Could not load campaigns."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCampaigns();
  }, [loadCampaigns]);

  return (
    <Card>
      <CardHeader title="Active campaigns" />
      <CardBody className="px-0 pb-0 pt-0">
        {loading && (
          <p className="px-6 py-8 text-sm text-zinc-500">Loading campaigns…</p>
        )}

        {error && (
          <p className="mx-6 my-6 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
            {error}
          </p>
        )}

        {!loading && !error && campaigns.length === 0 && (
          <p className="px-6 py-8 text-sm text-zinc-500">
            No campaigns yet. Click <strong className="text-zinc-300">New campaign</strong> to create one.
          </p>
        )}

        {!loading && !error && campaigns.length > 0 && (
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
        )}
      </CardBody>
    </Card>
  );
}
