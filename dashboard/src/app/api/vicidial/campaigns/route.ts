import { NextResponse } from "next/server";
import { ensureOrganizationForApi } from "@/lib/auth";
import { fetchVicidialCampaigns } from "@/lib/vicidial/campaigns";
import { resolveVicidialCreds } from "@/lib/vicidial/connection";

export async function GET() {
  const org = await ensureOrganizationForApi();
  const emptyOrg = { vicidial_url: null, vicidial_user: null, vicidial_pass: null };
  const { baseUrl, user, pass, userGroups, configured } = resolveVicidialCreds(org ?? emptyOrg);

  if (!configured) {
    return NextResponse.json(
      {
        error: "Connect ViciDial under Integrations first (server URL + API login).",
        campaigns: [],
      },
      { status: 400 },
    );
  }

  try {
    const campaigns = await fetchVicidialCampaigns({
      baseUrl,
      user,
      pass,
      userGroups,
    });
    return NextResponse.json({ campaigns });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Could not load campaigns from ViciDial.";
    return NextResponse.json({ error: message, campaigns: [] }, { status: 502 });
  }
}
