"use client";

import { useCallback, useEffect, useState } from "react";
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
import { formatSupabaseError } from "@/lib/errors";
import type { BotRow } from "@/lib/types/database";

function botStatus(status: string) {
  const map: Record<string, { label: string; variant: "live" | "warning" | "info" | "default" }> = {
    live: { label: "On call", variant: "live" },
    ringing: { label: "Ringing", variant: "warning" },
    dialing: { label: "Dialing", variant: "info" },
    idle: { label: "Idle", variant: "default" },
    offline: { label: "Offline", variant: "default" },
  };
  const s = map[status] ?? map.offline;
  return <Badge variant={s.variant} dot={s.variant !== "default"}>{s.label}</Badge>;
}

export function BotsTable() {
  const [bots, setBots] = useState<BotRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadBots = useCallback(async () => {
    if (!isSupabaseConfigured()) {
      setError("Add Supabase keys to .env.local and restart the dev server.");
      setLoading(false);
      return;
    }

    setLoading(true);
    setError("");

    try {
      const supabase = createClient();
      const { data, error: botsError } = await supabase
        .from("bots")
        .select("id, name, status, campaign_id, campaigns(name)")
        .order("name", { ascending: true });

      if (botsError) throw botsError;
      setBots((data ?? []) as BotRow[]);
    } catch (err) {
      setError(formatSupabaseError(err, "Could not load bots."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadBots();
  }, [loadBots]);

  return (
    <Card>
      <CardHeader title="All bots" description="Live status across campaigns" />
      <CardBody className="px-0 pb-0 pt-0">
        {loading && <p className="px-6 py-8 text-sm text-zinc-500">Loading bots…</p>}

        {error && (
          <p className="mx-6 my-6 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
            {error}
          </p>
        )}

        {!loading && !error && bots.length === 0 && (
          <p className="px-6 py-8 text-sm text-zinc-500">
            No bots assigned yet. Click{" "}
            <strong className="text-zinc-300">Assign to campaign</strong> to add one.
          </p>
        )}

        {!loading && !error && bots.length > 0 && (
          <Table>
            <TableHead>
              <TableHeaderCell>Bot ID</TableHeaderCell>
              <TableHeaderCell>Campaign</TableHeaderCell>
              <TableHeaderCell>Status</TableHeaderCell>
              <TableHeaderCell className="text-right">Calls/hr</TableHeaderCell>
              <TableHeaderCell className="text-right">Active now</TableHeaderCell>
            </TableHead>
            <TableBody>
              {bots.map((bot) => (
                <TableRow key={bot.id}>
                  <TableCell className="font-medium text-zinc-200">{bot.name}</TableCell>
                  <TableCell className="text-zinc-500">
                    {bot.campaigns?.name ?? "—"}
                  </TableCell>
                  <TableCell>{botStatus(bot.status)}</TableCell>
                  <TableCell className="text-right tabular-nums text-zinc-500">—</TableCell>
                  <TableCell className="text-right font-mono text-zinc-400">—</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardBody>
    </Card>
  );
}
