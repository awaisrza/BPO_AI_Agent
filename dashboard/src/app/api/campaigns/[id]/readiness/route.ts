import { NextResponse } from "next/server";
import { getCampaignReadiness } from "@/lib/campaign-readiness";
import { createClient } from "@/lib/supabase/server";
import { isSupabaseConfigured } from "@/lib/supabase/config";

type RouteParams = { params: Promise<{ id: string }> };

export async function GET(_request: Request, { params }: RouteParams) {
  if (!isSupabaseConfigured()) {
    return NextResponse.json({ error: "Supabase is not configured." }, { status: 503 });
  }

  const { id } = await params;
  const supabase = await createClient();
  const readiness = await getCampaignReadiness(supabase, id);
  return NextResponse.json(readiness);
}
