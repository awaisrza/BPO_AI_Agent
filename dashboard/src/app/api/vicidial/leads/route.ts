import { NextResponse } from "next/server";
import { ensureOrganizationForApi } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";
import { resolveVicidialCreds } from "@/lib/vicidial/connection";
import {
  fetchVicidialLeads,
  summarizeLeads,
  upsertVicidialLead,
} from "@/lib/vicidial/leads";
import { parseDialPhone } from "@/lib/vicidial/phone";

async function defaultVicidialCampaignId(): Promise<string> {
  const supabase = await createClient();
  const { data } = await supabase
    .from("campaigns")
    .select("vicidial_campaign_id")
    .not("vicidial_campaign_id", "is", null)
    .order("updated_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  return (
    data?.vicidial_campaign_id?.trim() ||
    process.env.VICIDIAL_DEFAULT_CAMPAIGN_ID?.trim() ||
    "test_cam"
  );
}

export async function GET(request: Request) {
  const org = await ensureOrganizationForApi();
  const emptyOrg = { vicidial_url: null, vicidial_user: null, vicidial_pass: null };
  const creds = resolveVicidialCreds(org ?? emptyOrg);
  if (!creds.configured) {
    return NextResponse.json(
      { error: "Connect ViciDial under Integrations first.", leads: [], summary: null },
      { status: 400 },
    );
  }

  const campaignId =
    new URL(request.url).searchParams.get("campaign_id")?.trim() ||
    (await defaultVicidialCampaignId());

  try {
    const { leads, detail } = await fetchVicidialLeads(
      { baseUrl: creds.baseUrl, user: creds.user, pass: creds.pass },
      { vicidialCampaignId: campaignId },
    );
    return NextResponse.json({
      leads,
      summary: summarizeLeads(leads),
      campaignId,
      detail,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Could not load leads.";
    return NextResponse.json(
      { error: message, leads: [], summary: null, campaignId },
      { status: 502 },
    );
  }
}

type Body = {
  phone?: string;
  campaign_id?: string;
  list_id?: string;
  status?: string;
  first_name?: string;
  last_name?: string;
};

export async function POST(request: Request) {
  const org = await ensureOrganizationForApi();
  const emptyOrg = { vicidial_url: null, vicidial_user: null, vicidial_pass: null };
  const creds = resolveVicidialCreds(org ?? emptyOrg);
  if (!creds.configured) {
    return NextResponse.json({ error: "Connect ViciDial under Integrations first." }, { status: 400 });
  }

  let body: Body = {};
  try {
    body = (await request.json()) as Body;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  const phoneRaw = body.phone?.trim();
  if (!phoneRaw) {
    return NextResponse.json({ error: "phone is required (e.g. +923142222318)." }, { status: 400 });
  }

  let parsed: { phone_code: string; phone_number: string };
  try {
    parsed = parseDialPhone(phoneRaw);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Invalid phone number." },
      { status: 400 },
    );
  }

  const campaignId =
    body.campaign_id?.trim() || (await defaultVicidialCampaignId());
  const listId =
    body.list_id?.trim() || process.env.VICIDIAL_DEFAULT_LIST_ID?.trim() || "101";

  const result = await upsertVicidialLead(
    { baseUrl: creds.baseUrl, user: creds.user, pass: creds.pass },
    {
      vicidialCampaignId: campaignId,
      phone_code: parsed.phone_code,
      phone_number: parsed.phone_number,
      list_id: listId,
      status: body.status?.trim() || "NEW",
      first_name: body.first_name,
      last_name: body.last_name,
    },
  );

  if (!result.ok) {
    return NextResponse.json({ error: result.detail }, { status: 502 });
  }

  const { leads, detail } = await fetchVicidialLeads(
    { baseUrl: creds.baseUrl, user: creds.user, pass: creds.pass },
    { vicidialCampaignId: campaignId },
  );

  return NextResponse.json({
    ok: true,
    message: result.detail,
    leads,
    summary: summarizeLeads(leads),
    campaignId,
    detail,
  });
}
