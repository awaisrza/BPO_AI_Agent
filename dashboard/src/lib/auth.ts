import { createClient } from "@/lib/supabase/server";
import type { OrganizationRow, ProfileRow } from "@/lib/types/database";

export async function getSessionUser() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  return user;
}

export async function getProfile(): Promise<ProfileRow | null> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return null;

  const { data } = await supabase
    .from("profiles")
    .select("id, org_id, email, name, role")
    .eq("id", user.id)
    .single();

  return data;
}

export async function getOrganization(): Promise<OrganizationRow | null> {
  const profile = await getProfile();
  if (!profile) return null;

  const supabase = await createClient();
  const { data } = await supabase
    .from("organizations")
    .select(
      "id, name, plan, vicidial_url, vicidial_user, vicidial_pass, transfer_preset, bots_included, minutes_included",
    )
    .eq("id", profile.org_id)
    .single();

  return data;
}
