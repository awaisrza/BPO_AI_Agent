import { NextResponse } from "next/server";
import { ensureOrganizationForApi, getProfile } from "@/lib/auth";
import { resolveVicidialCreds, testVicidialConnection } from "@/lib/vicidial/connection";

type TestBody = {
  vicidial_url?: string;
  vicidial_user?: string;
  vicidial_pass?: string;
};

export async function POST(request: Request) {
  let body: TestBody = {};
  try {
    body = (await request.json()) as TestBody;
  } catch {
    body = {};
  }

  const hasInlinePassword = Boolean(body.vicidial_pass?.trim());
  const org = await ensureOrganizationForApi();

  if (!org && !hasInlinePassword) {
    const profile = await getProfile();
    return NextResponse.json(
      {
        error: profile
          ? "Organization not found. Add SUPABASE_SERVICE_ROLE_KEY to .env.local or sign in again."
          : "Enter your API password to test, or sign in and save settings first.",
      },
      { status: 404 },
    );
  }

  const creds = resolveVicidialCreds(org ?? { vicidial_url: null, vicidial_user: null, vicidial_pass: null }, {
    vicidial_url: body.vicidial_url,
    vicidial_user: body.vicidial_user,
    vicidial_pass: body.vicidial_pass || undefined,
  });

  if (!creds.configured) {
    return NextResponse.json(
      {
        error: "Enter your ViciDial server URL, API user, and API password.",
      },
      { status: 400 },
    );
  }

  try {
    const result = await testVicidialConnection(creds);
    return NextResponse.json({
      ok: true,
      message: result.message,
      agentCount: result.agentCount,
    });
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Could not connect to ViciDial.";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
