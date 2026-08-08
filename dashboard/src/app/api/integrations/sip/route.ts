import { NextResponse } from "next/server";
import { ensureOrganizationForApi } from "@/lib/auth";
import { createAdminClient, isAdminConfigured } from "@/lib/supabase/admin";

function slugify(name: string): string {
  return (
    name
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "org"
  );
}

function sipDomain(): string {
  return process.env.SIP_EDGE_DOMAIN?.trim() || "bots.yourplatform.com";
}

function buildSipUri(agentUser: string, orgRef: string): string {
  const domain = sipDomain();
  return `sip:${agentUser.trim()}@${orgRef}.${domain}`;
}

export async function GET() {
  const domain = sipDomain();
  const org = await ensureOrganizationForApi();
  if (!org) {
    return NextResponse.json({
      domain,
      org_id: null,
      org_slug: null,
      template: `sip:{agent}@{org_ref}.${domain}`,
      bots: [],
    });
  }

  const orgRef = process.env.SIP_ORG_USE_UUID === "true" ? org.id : slugify(org.name);

  let bots: { id: string; name: string; agent_user: string; sip_uri: string }[] = [];
  if (isAdminConfigured()) {
    const admin = createAdminClient();
    const { data } = await admin
      .from("bots")
      .select("id, name, vicidial_agent_user")
      .eq("org_id", org.id)
      .order("name", { ascending: true });
    bots = (data ?? [])
      .filter((b) => (b.vicidial_agent_user ?? "").trim())
      .map((b) => ({
        id: b.id,
        name: b.name,
        agent_user: b.vicidial_agent_user!.trim(),
        sip_uri: buildSipUri(b.vicidial_agent_user!.trim(), orgRef),
      }));
  }

  return NextResponse.json({
    domain,
    org_id: org.id,
    org_slug: slugify(org.name),
    org_ref: orgRef,
    template: `sip:{agent}@${orgRef}.${domain}`,
    example: bots[0]?.sip_uri ?? buildSipUri("6666", orgRef),
    bots,
    note: "Point each ViciDial remote agent external address at the matching SIP URI. No AGI script on the BPO server.",
  });
}
