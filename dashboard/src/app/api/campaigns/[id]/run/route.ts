import { NextResponse } from "next/server";
import { setCampaignRunningStatus } from "@/lib/campaigns";
import { getCampaignReadiness } from "@/lib/campaign-readiness";
import { syncGpuSupervisor } from "@/lib/gpu/supervisor";
import { createClient } from "@/lib/supabase/server";
import { isSupabaseConfigured } from "@/lib/supabase/config";
import type { CampaignStatus } from "@/lib/types/database";

type RouteParams = { params: Promise<{ id: string }> };

type Body = { action?: "start" | "stop" };

export async function POST(request: Request, { params }: RouteParams) {
  if (!isSupabaseConfigured()) {
    return NextResponse.json({ error: "Supabase is not configured." }, { status: 503 });
  }

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

  if (action === "start") {
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

  await setCampaignRunningStatus(supabase, id, nextStatus);

  let supervisorMessage = "";
  try {
    const gpu = await syncGpuSupervisor(id, action);
    supervisorMessage = gpu.message;
  } catch (err) {
    supervisorMessage =
      err instanceof Error ? err.message : "Campaign updated but GPU supervisor sync failed.";
  }

  return NextResponse.json({
    ok: true,
    status: nextStatus,
    message: supervisorMessage || (nextStatus === "running" ? "Campaign is running." : "Campaign paused."),
  });
}
