import type { SupabaseClient } from "@supabase/supabase-js";
import { bootstrapUserProfile } from "@/lib/bootstrap-profile";
import { formatSupabaseError } from "@/lib/errors";

export async function getOrgId(supabase: SupabaseClient): Promise<string> {
  const {
    data: { user },
    error: userError,
  } = await supabase.auth.getUser();

  if (userError || !user) {
    throw new Error("Not signed in.");
  }

  const { data: profile, error: profileError } = await supabase
    .from("profiles")
    .select("org_id")
    .maybeSingle();

  if (profileError) {
    throw new Error(formatSupabaseError(profileError, "Could not load your profile."));
  }

  if (profile?.org_id) {
    const { data: org, error: orgError } = await supabase
      .from("organizations")
      .select("id")
      .eq("id", profile.org_id)
      .maybeSingle();

    if (!orgError && org) {
      return profile.org_id;
    }
  }

  const result = await bootstrapUserProfile(user, supabase);
  if (result.orgId) {
    return result.orgId;
  }

  throw new Error(
    result.error ??
      "Your account has no organization. Run dashboard/supabase/bootstrap-login.sql in Supabase, then try again.",
  );
}
