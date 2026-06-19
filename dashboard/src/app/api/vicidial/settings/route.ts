import { NextResponse } from "next/server";
import { ensureOrganizationForApi } from "@/lib/auth";
import { createAdminClient, isAdminConfigured } from "@/lib/supabase/admin";
import { normalizeVicidialUrl } from "@/lib/vicidial/connection";

type SaveBody = {
  vicidial_url?: string;
  vicidial_user?: string;
  vicidial_pass?: string;
};

function missingServiceRoleResponse() {
  return NextResponse.json(
    {
      error:
        "Cannot save without SUPABASE_SERVICE_ROLE_KEY. Add it to dashboard/.env.local (Supabase → Settings → API → service_role), restart npm run dev, then Save again.",
    },
    { status: 503 },
  );
}

export async function GET() {
  if (!isAdminConfigured()) {
    return NextResponse.json({
      vicidial_url: "",
      vicidial_user: "",
      password_set: false,
      configured: false,
      warning: "Add SUPABASE_SERVICE_ROLE_KEY to load saved ViciDial settings.",
    });
  }

  const org = await ensureOrganizationForApi();
  if (!org) {
    return NextResponse.json({
      vicidial_url: "",
      vicidial_user: "",
      password_set: false,
      configured: false,
    });
  }

  return NextResponse.json({
    vicidial_url: org.vicidial_url ?? "",
    vicidial_user: org.vicidial_user ?? "",
    password_set: Boolean(org.vicidial_pass),
    configured: Boolean(org.vicidial_url && org.vicidial_user && org.vicidial_pass),
  });
}

export async function PATCH(request: Request) {
  if (!isAdminConfigured()) {
    return missingServiceRoleResponse();
  }

  const admin = createAdminClient();
  if (!admin) {
    return missingServiceRoleResponse();
  }

  const org = await ensureOrganizationForApi();
  if (!org) {
    return NextResponse.json(
      {
        error:
          "Could not load organization from Supabase. Restart npm run dev after editing .env.local, or run dashboard/supabase/add-org-billing-columns.sql if migrations are incomplete.",
      },
      { status: 500 },
    );
  }

  let body: SaveBody = {};
  try {
    body = (await request.json()) as SaveBody;
  } catch {
    return NextResponse.json({ error: "Invalid request body." }, { status: 400 });
  }

  const url = normalizeVicidialUrl(body.vicidial_url ?? "");
  const user = body.vicidial_user?.trim() ?? "";
  if (!url || !user) {
    return NextResponse.json({ error: "Server URL and API user are required." }, { status: 400 });
  }

  const update: Record<string, string> = {
    vicidial_url: url,
    vicidial_user: user,
  };
  if (body.vicidial_pass?.trim()) {
    update.vicidial_pass = body.vicidial_pass.trim();
  } else if (!org.vicidial_pass) {
    return NextResponse.json({ error: "API password is required the first time." }, { status: 400 });
  }

  const { error } = await admin.from("organizations").update(update).eq("id", org.id);
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json({ ok: true });
}
