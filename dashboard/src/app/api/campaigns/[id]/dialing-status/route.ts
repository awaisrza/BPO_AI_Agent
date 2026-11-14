import { NextResponse } from "next/server";
import { setCampaignRunningStatus } from "@/lib/campaigns";
import { stopGpuForCampaign } from "@/lib/gpu/orchestrator";
import { createClient } from "@/lib/supabase/server";
import { isSupabaseConfigured } from "@/lib/supabase/config";
import { getVicidialCredsForCampaign } from "@/lib/vicidial/connection";
import {
  checkVicidialDialingDone,
  stopVicidialDialing,
} from "@/lib/vicidial/dialing";

type RouteParams = { params: Promise<{ id: string }> };

/**
 * Poll while a campaign is running. When the hopper is empty, no NEW dialable
 * leads remain, and the agent is not on a call, auto-pause (Pause → Run).
 */
export async function GET(_request: Request, { params }: RouteParams) {
  if (!isSupabaseConfigured()) {
    return NextResponse.json({ error: "Supabase is not configured." }, { status: 503 });
  }

  const { id } = await params;
  const supabase = await createClient();
  const { data: campaign } = await supabase
    .from("campaigns")
    .select("status, vicidial_campaign_id")
    .eq("id", id)
    .maybeSingle();

  if (!campaign) {
    return NextResponse.json({ error: "Campaign not found." }, { status: 404 });
  }

  const campaignStatus = (campaign.status as "running" | "paused") ?? "paused";
  const vicidialCampaignId = campaign.vicidial_campaign_id?.trim();
  if (!vicidialCampaignId) {
    return NextResponse.json({
      done: false,
      status: campaignStatus,
      detail: "No ViciDial campaign ID.",
    });
  }

  const { data: bots } = await supabase
    .from("bots")
    .select("vicidial_agent_user")
    .eq("campaign_id", id)
    .order("name", { ascending: true })
    .limit(1);
  const agentUser = bots?.[0]?.vicidial_agent_user?.trim();
  if (!agentUser) {
    return NextResponse.json({
      done: false,
      status: campaignStatus,
      detail: "No bot agent user.",
    });
  }

  const creds = await getVicidialCredsForCampaign(supabase, id);
  if (!creds.configured) {
    return NextResponse.json({
      done: false,
      status: campaignStatus,
      detail: "ViciDial not connected.",
    });
  }

  const check = await checkVicidialDialingDone(
    { baseUrl: creds.baseUrl, user: creds.user, pass: creds.pass },
    { vicidialCampaignId, agentUser },
  );

  if (!check.ok) {
    return NextResponse.json({
      done: false,
      status: campaignStatus,
      detail: check.detail,
    });
  }

  if (!check.done || campaignStatus !== "running") {
    return NextResponse.json({
      done: check.done,
      status: campaignStatus,
      detail: check.detail,
      autoPaused: false,
    });
  }

  const stop = await stopVicidialDialing(
    { baseUrl: creds.baseUrl, user: creds.user, pass: creds.pass },
    { vicidialCampaignId, agentUser },
  );
  await setCampaignRunningStatus(supabase, id, "paused");
  let gpuMessage = "";
  try {
    const gpu = await stopGpuForCampaign(id);
    gpuMessage = gpu.message;
  } catch (err) {
    gpuMessage = err instanceof Error ? err.message : "GPU stop skipped.";
  }

  return NextResponse.json({
    done: true,
    status: "paused",
    autoPaused: true,
    detail: check.detail,
    message: `All leads dialed — campaign paused. ${stop.message}${gpuMessage ? ` ${gpuMessage}` : ""}`,
  });
}
