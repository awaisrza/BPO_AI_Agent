"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Megaphone, Pause, Play } from "lucide-react";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Alert } from "@/components/ui/alert";
import { EmptyState } from "@/components/ui/empty-state";
import { Button } from "@/components/ui/button";
import { TableSkeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "@/components/ui/table";
import { createClient, isSupabaseConfigured, supabaseConfigHelp } from "@/lib/supabase/client";
import { setCampaignRunningStatus, toListItem, type CampaignListItem } from "@/lib/campaigns";
import { formatSupabaseError } from "@/lib/errors";
import type { CampaignRow, CampaignStatus } from "@/lib/types/database";

export function CampaignsTable() {
  const [campaigns, setCampaigns] = useState<CampaignListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

  const loadCampaigns = useCallback(async () => {
    if (!isSupabaseConfigured()) {
      setError(supabaseConfigHelp());
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

  async function toggleCampaignStatus(campaign: CampaignListItem) {
    setActionError("");
    setBusyId(campaign.id);

    try {
      if (campaign.status !== "running" && campaign.bots === 0) {
        throw new Error(`Assign at least one agent to "${campaign.name}" before running.`);
      }

      const supabase = createClient();
      const nextStatus: CampaignStatus = campaign.status === "running" ? "paused" : "running";
      await setCampaignRunningStatus(supabase, campaign.id, nextStatus);

      setCampaigns((prev) =>
        prev.map((c) => (c.id === campaign.id ? { ...c, status: nextStatus } : c)),
      );
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : formatSupabaseError(err, "Could not update campaign."),
      );
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Card>
      <CardHeader
        title="All campaigns"
        description={`${campaigns.length} campaign${campaigns.length === 1 ? "" : "s"}`}
      />
      <CardBody className="px-0 pb-0 pt-0">
        {loading && <TableSkeleton rows={4} cols={6} />}

        {error && (
          <div className="p-5">
            <Alert>{error}</Alert>
          </div>
        )}

        {actionError && (
          <div className="px-5 pb-4">
            <Alert variant="error">{actionError}</Alert>
          </div>
        )}

        {!loading && !error && campaigns.length === 0 && (
          <EmptyState
            icon={Megaphone}
            title="No campaigns yet"
            description="Create your first outbound campaign to configure scripts, knowledge base, and agent assignments."
            action={
              <Button href="/campaigns/new" size="sm">
                New campaign
              </Button>
            }
          />
        )}

        {!loading && !error && campaigns.length > 0 && (
          <Table>
            <TableHead>
              <TableHeaderCell>Campaign</TableHeaderCell>
              <TableHeaderCell>Script</TableHeaderCell>
              <TableHeaderCell>Agents</TableHeaderCell>
              <TableHeaderCell>Status</TableHeaderCell>
              <TableHeaderCell className="text-right">Dials</TableHeaderCell>
              <TableHeaderCell className="text-right">Transfer %</TableHeaderCell>
              <TableHeaderCell className="w-36 text-right">Actions</TableHeaderCell>
            </TableHead>
            <TableBody>
              {campaigns.map((c) => {
                const isBusy = busyId === c.id;
                return (
                <TableRow key={c.id}>
                  <TableCell className="font-medium text-foreground">{c.name}</TableCell>
                  <TableCell className="text-foreground-muted">{c.script}</TableCell>
                  <TableCell className="tabular-nums text-foreground-muted">{c.bots}</TableCell>
                  <TableCell>
                    <Badge
                      variant={c.status === "running" ? "live" : "default"}
                      dot={c.status === "running"}
                    >
                      {c.status === "running" ? "Running" : "Paused"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-foreground-muted">
                    {c.dials.toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-foreground-secondary">
                    {c.transferRate ? `${c.transferRate}%` : "—"}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-2">
                      {c.status === "running" ? (
                        <Button
                          variant="secondary"
                          size="sm"
                          disabled={isBusy}
                          onClick={() => toggleCampaignStatus(c)}
                        >
                          <Pause className="h-3.5 w-3.5" />
                          Pause
                        </Button>
                      ) : (
                        <Button
                          size="sm"
                          disabled={isBusy || c.bots === 0}
                          onClick={() => toggleCampaignStatus(c)}
                        >
                          <Play className="h-3.5 w-3.5" />
                          Run
                        </Button>
                      )}
                      <Link
                        href={`/campaigns/${c.id}`}
                        className="text-caption font-medium text-brand hover:text-brand-hover"
                      >
                        Edit
                      </Link>
                    </div>
                  </TableCell>
                </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </CardBody>
    </Card>
  );
}
