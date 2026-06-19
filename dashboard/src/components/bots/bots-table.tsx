"use client";

import { useCallback, useEffect, useState } from "react";
import { Bot } from "lucide-react";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Alert } from "@/components/ui/alert";
import { EmptyState } from "@/components/ui/empty-state";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/input";
import { TableSkeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "@/components/ui/table";
import { botStatusForCampaign } from "@/lib/campaigns";
import { createClient, isSupabaseConfigured, supabaseConfigHelp } from "@/lib/supabase/client";
import { formatSupabaseError } from "@/lib/errors";
import type { BotStatus, CampaignStatus } from "@/lib/types/database";

type CampaignOption = {
  id: string;
  name: string;
  status: CampaignStatus;
};

type BotListItem = {
  id: string;
  name: string;
  status: BotStatus;
  campaignId: string | null;
  campaignName: string;
  campaignStatus: CampaignStatus | null;
};

function botStatus(status: string) {
  const map: Record<string, { label: string; variant: "live" | "warning" | "info" | "default" }> = {
    live: { label: "On call", variant: "live" },
    ringing: { label: "Ringing", variant: "warning" },
    dialing: { label: "Dialing", variant: "info" },
    idle: { label: "Ready", variant: "live" },
    offline: { label: "Offline", variant: "default" },
  };
  const s = map[status] ?? map.offline;
  return <Badge variant={s.variant} dot={s.variant !== "default"}>{s.label}</Badge>;
}

export function BotsTable() {
  const [bots, setBots] = useState<BotListItem[]>([]);
  const [campaigns, setCampaigns] = useState<CampaignOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [busyBotId, setBusyBotId] = useState<string | null>(null);

  const loadBots = useCallback(async () => {
    if (!isSupabaseConfigured()) {
      setError(supabaseConfigHelp());
      setLoading(false);
      return;
    }

    setLoading(true);
    setError("");

    try {
      const supabase = createClient();

      const [{ data: botRows, error: botsError }, { data: campaignRows, error: campaignsError }] =
        await Promise.all([
          supabase.from("bots").select("id, name, status, campaign_id").order("name", { ascending: true }),
          supabase.from("campaigns").select("id, name, status").order("name"),
        ]);

      if (botsError) throw botsError;
      if (campaignsError) throw campaignsError;

      const campaignMap = Object.fromEntries(
        (campaignRows ?? []).map((c) => [c.id, { name: c.name, status: c.status as CampaignStatus }]),
      );

      setCampaigns(
        (campaignRows ?? []).map((c) => ({
          id: c.id,
          name: c.name,
          status: c.status as CampaignStatus,
        })),
      );

      setBots(
        (botRows ?? []).map((bot) => {
          const campaign = bot.campaign_id ? campaignMap[bot.campaign_id] : null;
          return {
            id: bot.id,
            name: bot.name,
            status: bot.status as BotStatus,
            campaignId: bot.campaign_id,
            campaignName: campaign?.name ?? "—",
            campaignStatus: campaign?.status ?? null,
          };
        }),
      );
    } catch (err) {
      setError(formatSupabaseError(err, "Could not load bots."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadBots();
  }, [loadBots]);

  async function reassignCampaign(botId: string, campaignId: string) {
    setActionError("");
    setBusyBotId(botId);

    try {
      const campaign = campaigns.find((c) => c.id === campaignId);
      const nextStatus = campaign ? botStatusForCampaign(campaign.status) : "offline";

      const supabase = createClient();
      const { error: updateError } = await supabase
        .from("bots")
        .update({ campaign_id: campaignId, status: nextStatus })
        .eq("id", botId);

      if (updateError) throw updateError;

      setBots((prev) =>
        prev.map((bot) =>
          bot.id === botId
            ? {
                ...bot,
                campaignId,
                campaignName: campaign?.name ?? "—",
                campaignStatus: campaign?.status ?? null,
                status: nextStatus,
              }
            : bot,
        ),
      );
    } catch (err) {
      setActionError(formatSupabaseError(err, "Could not reassign agent."));
    } finally {
      setBusyBotId(null);
    }
  }

  return (
    <div className="space-y-4">
      <Alert variant="info">
        <strong className="text-foreground">How to go live:</strong> (1) Assign each agent to a
        campaign below. (2) Open <strong>Campaigns</strong> and click <strong>Run</strong> — all
        assigned agents go live automatically. Dialing starts when ViciDial is connected under
        Integrations.
      </Alert>

      <Card>
        <CardHeader
          title="Agent roster"
          description={`${bots.length} agent${bots.length === 1 ? "" : "s"} · real-time status`}
        />
        <CardBody className="px-0 pb-0 pt-0">
          {loading && <TableSkeleton rows={5} cols={5} />}

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

          {!loading && !error && bots.length === 0 && (
            <EmptyState
              icon={Bot}
              title="No agents assigned"
              description="Assign AI agents to campaigns to start handling outbound calls."
              action={
                <Button href="/bots/assign" variant="secondary" size="sm">
                  Assign to campaign
                </Button>
              }
            />
          )}

          {!loading && !error && bots.length > 0 && (
            <Table>
              <TableHead>
                <TableHeaderCell>Agent ID</TableHeaderCell>
                <TableHeaderCell>Campaign</TableHeaderCell>
                <TableHeaderCell>Status</TableHeaderCell>
                <TableHeaderCell className="text-right">Calls/hr</TableHeaderCell>
                <TableHeaderCell className="text-right">Active now</TableHeaderCell>
              </TableHead>
              <TableBody>
                {bots.map((bot) => {
                  const isBusy = busyBotId === bot.id;

                  return (
                    <TableRow key={bot.id}>
                      <TableCell className="font-medium text-foreground">{bot.name}</TableCell>
                      <TableCell>
                        {campaigns.length === 0 ? (
                          <span className="text-foreground-muted">No campaigns</span>
                        ) : (
                          <Select
                            className="w-full min-w-[10rem] text-sm"
                            value={bot.campaignId ?? ""}
                            disabled={isBusy}
                            onChange={(e) => reassignCampaign(bot.id, e.target.value)}
                          >
                            {!bot.campaignId && (
                              <option value="" disabled>
                                Select campaign
                              </option>
                            )}
                            {campaigns.map((c) => (
                              <option key={c.id} value={c.id}>
                                {c.name}
                                {c.status === "running" ? " · Running" : ""}
                              </option>
                            ))}
                          </Select>
                        )}
                      </TableCell>
                      <TableCell>{botStatus(bot.status)}</TableCell>
                      <TableCell className="text-right tabular-nums text-foreground-faint">—</TableCell>
                      <TableCell className="text-right font-mono text-caption text-foreground-faint">—</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
