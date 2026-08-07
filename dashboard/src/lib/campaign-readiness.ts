import type { SupabaseClient } from "@supabase/supabase-js";
import { resolveVicidialCreds } from "@/lib/vicidial/connection";

export type CampaignReadinessIssue = {
  level: "error" | "warning";
  message: string;
};

export type CampaignReadiness = {
  ready: boolean;
  issues: CampaignReadinessIssue[];
  botCount: number;
  vicidialConfigured: boolean;
  vicidialCampaignId: string | null;
};

type BotRow = {
  id: string;
  name: string;
  vicidial_agent_user: string | null;
};

type OrgVicidial = {
  vicidial_url: string | null;
  vicidial_user: string | null;
  vicidial_pass: string | null;
};

type CampaignQueryRow = {
  id: string;
  name: string;
  vicidial_campaign_id: string | null;
  org_id: string;
  organizations: OrgVicidial | OrgVicidial[] | null;
};

function orgFromCampaign(row: CampaignQueryRow): OrgVicidial | null {
  const org = row.organizations;
  if (!org) return null;
  return Array.isArray(org) ? (org[0] ?? null) : org;
}

/** Validate dashboard + ViciDial mapping before Run campaign. */
export async function getCampaignReadiness(
  supabase: SupabaseClient,
  campaignId: string,
): Promise<CampaignReadiness> {
  const issues: CampaignReadinessIssue[] = [];

  const { data: campaign, error: campaignError } = await supabase
    .from("campaigns")
    .select(
      "id, name, vicidial_campaign_id, org_id, organizations(vicidial_url, vicidial_user, vicidial_pass)",
    )
    .eq("id", campaignId)
    .single();

  if (campaignError || !campaign) {
    return {
      ready: false,
      issues: [{ level: "error", message: "Campaign not found." }],
      botCount: 0,
      vicidialConfigured: false,
      vicidialCampaignId: null,
    };
  }

  const row = campaign as CampaignQueryRow;
  const org = orgFromCampaign(row);
  const { configured: vicidialConfigured } = resolveVicidialCreds(
    org ?? { vicidial_url: null, vicidial_user: null, vicidial_pass: null },
  );

  if (!vicidialConfigured) {
    issues.push({
      level: "error",
      message: "ViciDial is not connected. Open Integrations and save your dialer URL + API login.",
    });
  }

  const vicidialCampaignId = row.vicidial_campaign_id?.trim() || null;
  if (!vicidialCampaignId) {
    issues.push({
      level: "error",
      message: "Set the ViciDial campaign ID (must match the campaign in their dialer hopper).",
    });
  }

  const { data: bots, error: botsError } = await supabase
    .from("bots")
    .select("id, name, vicidial_agent_user")
    .eq("campaign_id", campaignId);

  if (botsError) {
    issues.push({ level: "error", message: "Could not load assigned agents." });
  }

  const botRows = (bots ?? []) as BotRow[];
  if (botRows.length === 0) {
    issues.push({
      level: "error",
      message: "Assign at least one agent under Bots before running this campaign.",
    });
  }

  for (const bot of botRows) {
    if (!bot.vicidial_agent_user?.trim()) {
      issues.push({
        level: "error",
        message: `Agent "${bot.name}" has no ViciDial login — set it under Bots → Assign or edit the roster.`,
      });
    }
  }

  issues.push({
    level: "warning",
    message:
      "Ensure closers are logged into ViciDial and your GPU fleet supervisor is running (audio bridge).",
  });

  const hasErrors = issues.some((i) => i.level === "error");

  return {
    ready: !hasErrors,
    issues,
    botCount: botRows.length,
    vicidialConfigured,
    vicidialCampaignId,
  };
}
