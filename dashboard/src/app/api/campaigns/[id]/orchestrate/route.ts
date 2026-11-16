import { NextResponse } from "next/server";
import { getProfile } from "@/lib/auth";
import { startGpuForCampaign, stopGpuForCampaign } from "@/lib/gpu/orchestrator";
import { createClient } from "@/lib/supabase/server";

type Body = {
  action?: "start" | "stop";
};

async function userOwnsCampaign(campaignId: string): Promise<boolean> {
  const profile = await getProfile();
  if (!profile?.org_id) return false;

  const supabase = await createClient();
  const { data } = await supabase
    .from("campaigns")
    .select("id")
    .eq("id", campaignId)
    .eq("org_id", profile.org_id)
    .maybeSingle();

  return Boolean(data);
}

export async function POST(
  request: Request,
  context: { params: Promise<{ id: string }> },
) {
  const { id: campaignId } = await context.params;

  if (!(await userOwnsCampaign(campaignId))) {
    return NextResponse.json({ error: "Campaign not found." }, { status: 404 });
  }

  let body: Body = {};
  try {
    body = (await request.json()) as Body;
  } catch {
    return NextResponse.json({ error: "Invalid request body." }, { status: 400 });
  }

  const action = body.action;
  if (action !== "start" && action !== "stop") {
    return NextResponse.json({ error: 'action must be "start" or "stop".' }, { status: 400 });
  }

  try {
    const result =
      action === "start"
        ? await startGpuForCampaign(campaignId)
        : await stopGpuForCampaign(campaignId);

    return NextResponse.json(result);
  } catch (err) {
    const message = err instanceof Error ? err.message : "GPU orchestration failed.";
    return NextResponse.json({ ok: false, configured: true, error: message }, { status: 502 });
  }
}
