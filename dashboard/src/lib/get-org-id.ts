import type { SupabaseClient } from "@supabase/supabase-js";
import { formatSupabaseError } from "@/lib/errors";

export async function getOrgId(supabase: SupabaseClient): Promise<string> {
  const { data: profile, error: profileError } = await supabase
    .from("profiles")
    .select("org_id")
    .maybeSingle();

  if (profileError) {
    throw new Error(formatSupabaseError(profileError, "Could not load your profile."));
  }

  if (profile?.org_id) {
    return profile.org_id;
  }

  const { data: orgId, error: rpcError } = await supabase.rpc("ensure_user_profile");

  if (rpcError) {
    throw new Error(
      formatSupabaseError(
        rpcError,
        "Your account has no organization. Run supabase/fix-missing-profile.sql in Supabase, then try again.",
      ),
    );
  }

  if (!orgId) {
    throw new Error("Could not set up your organization. Sign out and sign in again.");
  }

  return orgId as string;
}
