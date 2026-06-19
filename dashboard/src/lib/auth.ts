import { createClient } from "@/lib/supabase/server";
import { isSupabaseConfigured } from "@/lib/supabase/config";
import { bootstrapUserProfile } from "@/lib/bootstrap-profile";
import type { OrganizationRow, ProfileRow } from "@/lib/types/database";
export async function getSessionUser() {
  if (!isSupabaseConfigured()) return null;

  try {
    const supabase = await createClient();
    const {
      data: { user },
    } = await supabase.auth.getUser();
    return user;
  } catch {
    return null;
  }
}

export async function getProfile(): Promise<ProfileRow | null> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return null;

  const { data, error } = await supabase
    .from("profiles")
    .select("id, org_id, email, name, role")
    .eq("id", user.id)
    .maybeSingle();

  if (error) return null;
  return data;
}

/** Create org + profile for accounts that exist in auth but not in profiles. */
export async function ensureUserProfile(): Promise<string | null> {
  const user = await getSessionUser();
  if (!user) return null;

  const existing = await getProfile();
  if (existing?.org_id) {
    const org = await getOrganization();
    if (org) return existing.org_id;
  }

  try {
    const supabase = await createClient();
    const result = await bootstrapUserProfile(user, supabase);
    return result.orgId;
  } catch {
    return null;
  }
}
export async function getOrganization(): Promise<OrganizationRow | null> {
  const profile = await getProfile();
  if (!profile) return null;

  const supabase = await createClient();
  const { data, error } = await supabase
    .from("organizations")
    .select(
      "id, name, plan, vicidial_url, vicidial_user, vicidial_pass, transfer_preset",
    )
    .eq("id", profile.org_id)
    .maybeSingle();

  if (error || !data) return null;
  return data;
}

const ORG_API_SELECT =
  "id, name, plan, vicidial_url, vicidial_user, vicidial_pass, transfer_preset";

async function findOrgIdFromExistingData(
  admin: NonNullable<Awaited<ReturnType<typeof import("@/lib/supabase/admin").createAdminClient>>>,
): Promise<string | null> {
  for (const table of ["campaigns", "bots", "profiles"] as const) {
    const { data } = await admin.from(table).select("org_id").not("org_id", "is", null).limit(1);
    const orgId = data?.[0]?.org_id;
    if (typeof orgId === "string" && orgId) return orgId;
  }
  return null;
}

async function fetchOrganizationById(orgId: string): Promise<OrganizationRow | null> {
  const { createAdminClient } = await import("@/lib/supabase/admin");
  const admin = createAdminClient();
  if (!admin) return null;

  const { data } = await admin
    .from("organizations")
    .select(ORG_API_SELECT)
    .eq("id", orgId)
    .maybeSingle();

  return data ?? null;
}

/** Pilot fallback when auth/profile is missing — uses service role to load the best org match. */
export async function getOrganizationForApi(orgId?: string): Promise<OrganizationRow | null> {
  if (orgId) {
    return fetchOrganizationById(orgId);
  }

  const org = await getOrganization();
  if (org) return org;

  const { createAdminClient } = await import("@/lib/supabase/admin");
  const admin = createAdminClient();
  if (!admin) return null;

  // Prefer org that already has ViciDial saved (not the arbitrary first row).
  const { data: vicidialOrgs } = await admin
    .from("organizations")
    .select(ORG_API_SELECT)
    .not("vicidial_url", "is", null)
    .neq("vicidial_url", "")
    .limit(1);
  if (vicidialOrgs?.[0]) return vicidialOrgs[0];

  const linkedOrgId = await findOrgIdFromExistingData(admin);
  if (linkedOrgId) {
    const linked = await fetchOrganizationById(linkedOrgId);
    if (linked) return linked;
  }

  const { data: rows, error } = await admin.from("organizations").select(ORG_API_SELECT).limit(1);
  if (error || !rows?.length) return null;
  return rows[0];
}

export async function getOrganizationForCampaign(campaignId: string): Promise<OrganizationRow | null> {
  const { createAdminClient } = await import("@/lib/supabase/admin");
  const admin = createAdminClient();
  if (!admin) return getOrganizationForApi();

  const { data: campaign } = await admin
    .from("campaigns")
    .select("org_id")
    .eq("id", campaignId)
    .maybeSingle();

  if (campaign?.org_id) {
    return getOrganizationForApi(campaign.org_id);
  }

  return getOrganizationForApi();
}

/** Resolve org for server API routes; creates one if the DB has data but no org row yet. */
export async function ensureOrganizationForApi(): Promise<OrganizationRow | null> {
  const existing = await getOrganizationForApi();
  if (existing) return existing;

  const { createAdminClient } = await import("@/lib/supabase/admin");
  const admin = createAdminClient();
  if (!admin) return null;

  const linkedOrgId = await findOrgIdFromExistingData(admin);
  if (linkedOrgId) {
    const linked = await getOrganizationForApi(linkedOrgId);
    if (linked) return linked;
  }

  const { data: created, error } = await admin
    .from("organizations")
    .insert({ name: "My Call Center" })
    .select(ORG_API_SELECT)
    .single();

  if (error || !created) return null;
  return created;
}

export type OrgSummary = {
  name: string;
  plan: string;
  botsIncluded: number;
  botsActive: number;
  pilot: boolean;
};

export const DEFAULT_ORG_SUMMARY: OrgSummary = {
  name: "My Call Center",
  plan: "pilot",
  botsIncluded: 10,
  botsActive: 0,
  pilot: true,
};

export async function getOrgSummary(): Promise<OrgSummary | null> {
  let org = await getOrganization();
  if (!org) {
    await ensureUserProfile();
    org = await getOrganization();
  }
  if (!org) return null;

  const supabase = await createClient();
  const { count, error: botsError } = await supabase
    .from("bots")
    .select("*", { count: "exact", head: true });

  return {
    name: org.name,
    plan: org.plan,
    botsIncluded: org.bots_included ?? 10,
    botsActive: botsError ? 0 : (count ?? 0),
    pilot: org.plan === "pilot",
  };
}
