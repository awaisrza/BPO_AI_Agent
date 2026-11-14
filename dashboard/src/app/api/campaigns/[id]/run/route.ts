import { NextResponse } from "next/server";
import { setCampaignRunningStatus } from "@/lib/campaigns";
import { getCampaignReadiness } from "@/lib/campaign-readiness";
import { startGpuForCampaign, stopGpuForCampaign } from "@/lib/gpu/orchestrator";
import { createClient } from "@/lib/supabase/server";
import { isSupabaseConfigured } from "@/lib/supabase/config";
import type { CampaignStatus } from "@/lib/types/database";
import type { VicidialCredentials } from "@/lib/vicidial/closers";
import { getVicidialCredsForCampaign } from "@/lib/vicidial/connection";
import {
  startVicidialDialing,
  stopVicidialDialing,
  type DialingResult,
} from "@/lib/vicidial/dialing";

type RouteParams = { params: Promise<{ id: string }> };

type Body = { action?: "start" | "stop" };

type DialerContext =
  | {
      ok: true;
      creds: VicidialCredentials;
      input: { vicidialCampaignId: string; agentUser: string };
    }
  | { ok: false; error: string };

async function dialerContext(
  supabase: Awaited<ReturnType<typeof createClient>>,
  campaignId: string,
): Promise<DialerContext> {
  const { data: campaign } = await supabase
    .from("campaigns")
    .select("vicidial_campaign_id")
    .eq("id", campaignId)
    .maybeSingle();
  const vicidialCampaignId = campaign?.vicidial_campaign_id?.trim();
  if (!vicidialCampaignId) {
    return {
      ok: false,
      error: "Set the ViciDial campaign ID (e.g. test_cam) and save first.",
    };
  }
  const { data: bots } = await supabase
    .from("bots")
    .select("vicidial_agent_user")
    .eq("campaign_id", campaignId)
    .order("name", { ascending: true })
    .limit(1);
  const agentUser = bots?.[0]?.vicidial_agent_user?.trim();
  if (!agentUser) {
    return {
      ok: false,
      error: "Assign a bot with a ViciDial agent login (e.g. 6666) first.",
    };
  }
  const creds = await getVicidialCredsForCampaign(supabase, campaignId);
  if (!creds.configured) {
    return {
      ok: false,
      error: "ViciDial is not connected. Save dialer credentials under Integrations.",
    };
  }
  return {
    ok: true,
    creds: { baseUrl: creds.baseUrl, user: creds.user, pass: creds.pass },
    input: { vicidialCampaignId, agentUser },
  };
}

export async function POST(request: Request, { params }: RouteParams) {
  if (!isSupabaseConfigured()) {
    return NextResponse.json({ error: "Supabase is not configured." }, { status: 503 });
  }

  let dialingResult: DialingResult | null = null;
  try {
    const { id } = await params;
    let body: Body = {};
    try {
      body = (await request.json()) as Body;
    } catch {
      body = {};
    }

    const action = body.action ?? "start";
    const nextStatus: CampaignStatus = action === "start" ? "running" : "paused";

    const supabase = await createClient();
    const dialer = await dialerContext(supabase, id);

    if (action === "stop" && dialer.ok) {
      dialingResult = await stopVicidialDialing(dialer.creds, dialer.input);
    }

    if (action === "start") {
      if (!dialer.ok) {
        return NextResponse.json({ error: dialer.error }, { status: 400 });
      }
      const readiness = await getCampaignReadiness(supabase, id);
      if (!readiness.ready) {
        return NextResponse.json(
          {
            error: readiness.issues
              .filter((i) => i.level === "error")
              .map((i) => i.message)
              .join(" "),
            readiness,
          },
          { status: 400 },
        );
      }
    }

    const statusUpdate = await setCampaignRunningStatus(supabase, id, nextStatus);
    if (!statusUpdate.ok) {
      return NextResponse.json(
        {
          error:
            statusUpdate.error ??
            "Could not update campaign status. Check Supabase RLS policies for campaigns/bots.",
        },
        { status: 403 },
      );
    }

    let supervisorMessage = "";
    try {
      const gpu = action === "start" ? await startGpuForCampaign(id) : await stopGpuForCampaign(id);
      supervisorMessage = gpu.message;
    } catch (err) {
      supervisorMessage =
        err instanceof Error ? err.message : "Campaign updated but GPU orchestration failed.";
    }

    if (action === "start" && dialer.ok) {
      dialingResult = await startVicidialDialing(dialer.creds, dialer.input);
    }

    return NextResponse.json(
      {
        ok: dialingResult ? dialingResult.ok : true,
        status: nextStatus,
        message:
          dialingResult?.message ||
          supervisorMessage ||
          (nextStatus === "running" ? "Campaign is running." : "Campaign paused."),
        gpuMessage: supervisorMessage,
        steps: dialingResult?.steps ?? [],
      },
      {
        status: dialingResult && !dialingResult.ok && action === "start" ? 502 : 200,
      },
    );
  } catch (err) {
    const message = err instanceof Error ? err.message : "Could not update campaign status.";
    console.error("[campaign-run]", err);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
