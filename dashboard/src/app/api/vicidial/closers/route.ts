import { NextResponse } from "next/server";
import { ensureOrganizationForApi, getOrganizationForCampaign } from "@/lib/auth";
import { fetchVicidialClosers } from "@/lib/vicidial/closers";
import { resolveVicidialCreds } from "@/lib/vicidial/connection";

export async function GET(request: Request) {
  const campaignId = new URL(request.url).searchParams.get("campaignId")?.trim();
  const org = campaignId
    ? await getOrganizationForCampaign(campaignId)
    : await ensureOrganizationForApi();

  const emptyOrg = { vicidial_url: null, vicidial_user: null, vicidial_pass: null };
  const { baseUrl, user, pass, userGroups, configured } = resolveVicidialCreds(org ?? emptyOrg);

  if (!configured) {
    const needsServiceKey = !org;
    return NextResponse.json(
      {
        error: needsServiceKey
          ? "Organization not found. Add SUPABASE_SERVICE_ROLE_KEY to dashboard/.env.local, save ViciDial under Integrations, then refresh."
          : "ViciDial is not connected yet. Add your dialer URL and API login under Integrations.",
        closers: [],
      },
      { status: needsServiceKey ? 404 : 400 },
    );
  }

  try {
    const closers = await fetchVicidialClosers({
      baseUrl,
      user,
      pass,
      userGroups,
    });

    return NextResponse.json({ closers });
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Could not load closers from ViciDial.";
    if (message.includes("NO LOGGED IN AGENTS")) {
      return NextResponse.json({ closers: [] });
    }
    return NextResponse.json({ error: message, closers: [] }, { status: 502 });
  }
}
