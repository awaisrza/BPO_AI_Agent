import { NextResponse } from "next/server";
import { setCampaignRunningStatus } from "@/lib/campaigns";
import { fetchGpuWarmupStatus, startGpuWarmup } from "@/lib/gpu/warmup";
import { createClient } from "@/lib/supabase/server";
import { isSupabaseConfigured } from "@/lib/supabase/config";

type RouteParams = { params: Promise<{ id: string }> };

async function campaignBotId(supabase: Awaited<ReturnType<typeof createClient>>, campaignId: string) {
  const { data: bots } = await supabase
    .from("bots")
    .select("id")
    .eq("campaign_id", campaignId)
    .order("name", { ascending: true })
    .limit(1);
  return bots?.[0]?.id ?? null;
}

/** Poll GPU supervisor + worker /health (use while test dial waits for prewarm). */
export async function GET(_request: Request, { params }: RouteParams) {
  if (!isSupabaseConfigured()) {
    return NextResponse.json({ error: "Supabase is not configured." }, { status: 503 });
  }

  const { id } = await params;
  const supabase = await createClient();
  const botId = await campaignBotId(supabase, id);
  const status = await fetchGpuWarmupStatus({ campaignId: id, botId: botId ?? undefined });

  return NextResponse.json({
    ...status,
    botId,
  });
}

/** Set campaign running and nudge GPU supervisor before test dial. */
export async function POST(_request: Request, { params }: RouteParams) {
  if (!isSupabaseConfigured()) {
    return NextResponse.json({ error: "Supabase is not configured." }, { status: 503 });
  }

  const { id } = await params;
  const supabase = await createClient();

  const statusUpdate = await setCampaignRunningStatus(supabase, id, "running");
  const gpu = await startGpuWarmup(id);
  const botId = await campaignBotId(supabase, id);
  const warmup = await fetchGpuWarmupStatus({ campaignId: id, botId: botId ?? undefined });

  return NextResponse.json({
    ok: true,
    campaignStatus: statusUpdate.ok ? "running" : statusUpdate.error,
    gpuMessage: gpu.message,
    botId,
    ...warmup,
  });
}
