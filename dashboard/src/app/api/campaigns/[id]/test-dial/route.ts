import { NextResponse } from "next/server";
import { setCampaignRunningStatus } from "@/lib/campaigns";
import { getCampaignReadiness } from "@/lib/campaign-readiness";
import { syncGpuSupervisor } from "@/lib/gpu/supervisor";
import { checkGpuWorkerHealth } from "@/lib/gpu/worker-health";
import { createClient } from "@/lib/supabase/server";
import { isSupabaseConfigured } from "@/lib/supabase/config";
import { parseDialPhone } from "@/lib/vicidial/phone";
import { getVicidialCredsForCampaign } from "@/lib/vicidial/connection";
import { runVicidialTestDial } from "@/lib/vicidial/test-dial";

type RouteParams = { params: Promise<{ id: string }> };

type Body = {
  phone?: string;
  list_id?: string;
  outbound_cid?: string;
  start_campaign?: boolean;
};

export async function POST(request: Request, { params }: RouteParams) {
  if (!isSupabaseConfigured()) {
    return NextResponse.json({ error: "Supabase is not configured." }, { status: 503 });
  }

  try {
    const { id } = await params;
    let body: Body = {};
    try {
      body = (await request.json()) as Body;
    } catch {
      return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
    }

    const phoneRaw = body.phone?.trim();
    if (!phoneRaw) {
      return NextResponse.json({ error: "phone is required (e.g. +923142222318)." }, { status: 400 });
    }

    const supabase = await createClient();
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

    const { data: bots, error: botsError } = await supabase
      .from("bots")
      .select("vicidial_agent_user")
      .eq("campaign_id", id)
      .order("name", { ascending: true })
      .limit(1);

    if (botsError || !bots?.length) {
      return NextResponse.json({ error: "No assigned agents for this campaign." }, { status: 400 });
    }

    const remoteAgentUser = bots[0]?.vicidial_agent_user?.trim();
    if (!remoteAgentUser) {
      return NextResponse.json(
        { error: "Assigned agent has no ViciDial login — set it under Bots." },
        { status: 400 },
      );
    }

    const listId =
      body.list_id?.trim() ||
      process.env.VICIDIAL_DEFAULT_LIST_ID?.trim() ||
      "";
    if (!listId) {
      return NextResponse.json(
        {
          error:
            "list_id is required — enter the ViciDial lead list ID for this campaign (e.g. 101).",
        },
        { status: 400 },
      );
    }

    let parsedPhone: { phone_code: string; phone_number: string };
    try {
      parsedPhone = parseDialPhone(phoneRaw);
    } catch (err) {
      return NextResponse.json(
        { error: err instanceof Error ? err.message : "Invalid phone number." },
        { status: 400 },
      );
    }

    const creds = await getVicidialCredsForCampaign(supabase, id);
    if (!creds.configured) {
      return NextResponse.json(
        { error: "ViciDial is not connected. Save dialer credentials under Integrations." },
        { status: 400 },
      );
    }

    const startCampaign = body.start_campaign !== false;

    let gpuMessage = "";
    if (startCampaign) {
      const statusUpdate = await setCampaignRunningStatus(supabase, id, "running");
      if (!statusUpdate.ok) {
        gpuMessage = `Campaign status not updated in dashboard (${statusUpdate.error ?? "permission denied"}) — continuing with ViciDial test dial. `;
      }
      try {
        const gpu = await syncGpuSupervisor(id, "start");
        gpuMessage += gpu.configured
          ? gpu.message
          : `${gpu.message} Campaign status is running — GPU supervisor will sync on its next poll (~20s).`;
      } catch (err) {
        gpuMessage +=
          (err instanceof Error ? err.message : "GPU supervisor sync failed.") +
          " If the supervisor poll loop is active on the GPU, the worker should still start.";
      }
    }

    const workerHealth = startCampaign ? await checkGpuWorkerHealth() : null;

    const result = await runVicidialTestDial(
      { baseUrl: creds.baseUrl, user: creds.user, pass: creds.pass },
      {
        vicidialCampaignId: readiness.vicidialCampaignId!,
        remoteAgentUser,
        phone_code: parsedPhone.phone_code,
        phone_number: parsedPhone.phone_number,
        list_id: listId,
        outbound_cid: body.outbound_cid?.trim(),
      },
    );

    return NextResponse.json(
      {
        ok: result.ok,
        message: result.message,
        gpuMessage,
        workerHealth: workerHealth?.message ?? "",
        workerHealthy: workerHealth?.ok ?? null,
        steps: result.steps,
        hopperPreview: result.hopperPreview,
        dialed: `+${parsedPhone.phone_code}${parsedPhone.phone_number}`,
        campaignStarted: startCampaign,
      },
      { status: result.ok ? 200 : 502 },
    );
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Test dial failed due to an unexpected server error.";
    console.error("[test-dial]", err);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
