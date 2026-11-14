import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { isSupabaseConfigured } from "@/lib/supabase/config";

type RouteParams = { params: Promise<{ id: string }> };

export async function GET(_request: Request, { params }: RouteParams) {
  if (!isSupabaseConfigured()) {
    return NextResponse.json({ error: "Supabase is not configured." }, { status: 503 });
  }

  const { id } = await params;
  if (!id?.trim()) {
    return NextResponse.json({ error: "Call id required." }, { status: 400 });
  }

  const supabase = await createClient();
  const { data, error } = await supabase
    .from("calls")
    .select(
      "id, phone, duration_sec, outcome, disposition, transferred, sentiment, transcript_json, created_at, campaigns(name)",
    )
    .eq("id", id)
    .maybeSingle();

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  if (!data) {
    return NextResponse.json({ error: "Call not found." }, { status: 404 });
  }

  const raw = data.transcript_json;
  const transcript = Array.isArray(raw)
    ? raw
        .map((line) => {
          if (!line || typeof line !== "object") return null;
          const role = String((line as { role?: string }).role ?? "").toLowerCase();
          const text = String((line as { text?: string }).text ?? "").trim();
          if (!text) return null;
          return {
            role: role === "bot" || role === "agent" ? "bot" : "caller",
            text,
          };
        })
        .filter(Boolean)
    : [];

  return NextResponse.json({
    call: {
      ...data,
      transcript,
    },
  });
}
