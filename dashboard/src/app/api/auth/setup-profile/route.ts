import { NextResponse } from "next/server";
import { bootstrapUserProfile } from "@/lib/bootstrap-profile";
import { getSessionUser } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";

export async function POST() {
  const user = await getSessionUser();
  if (!user) {
    return NextResponse.json({ error: "Not signed in." }, { status: 401 });
  }

  const supabase = await createClient();
  const result = await bootstrapUserProfile(user, supabase);

  if (!result.orgId) {
    return NextResponse.json(
      { error: result.error ?? "Could not set up workspace." },
      { status: 500 },
    );
  }

  return NextResponse.json({ orgId: result.orgId, method: result.method });
}
