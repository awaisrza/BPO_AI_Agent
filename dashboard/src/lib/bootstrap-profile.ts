import type { SupabaseClient, User } from "@supabase/supabase-js";
import { createAdminClient } from "@/lib/supabase/admin";
import { formatSupabaseError } from "@/lib/errors";

export type BootstrapResult = {
  orgId: string | null;
  error?: string;
  method?: "existing" | "admin" | "rpc";
};

function orgNameFromUser(user: User) {
  const meta = user.user_metadata ?? {};
  return (
    (typeof meta.org_name === "string" && meta.org_name.trim()) ||
    (typeof meta.company === "string" && meta.company.trim()) ||
    "My Call Center"
  );
}

function displayNameFromUser(user: User) {
  const meta = user.user_metadata ?? {};
  const email = user.email ?? "";
  return (
    (typeof meta.name === "string" && meta.name.trim()) ||
    (typeof meta.full_name === "string" && meta.full_name.trim()) ||
    email.split("@")[0] ||
    "Admin"
  );
}

async function bootstrapWithAdmin(user: User): Promise<BootstrapResult> {
  const admin = createAdminClient();
  if (!admin) {
    return { orgId: null, error: "Service role key not configured." };
  }

  const { data: existingProfile, error: profileReadError } = await admin
    .from("profiles")
    .select("org_id")
    .eq("id", user.id)
    .maybeSingle();

  if (profileReadError) {
    return {
      orgId: null,
      error: formatSupabaseError(profileReadError, "Could not read profile."),
    };
  }

  if (existingProfile?.org_id) {
    const { data: org, error: orgReadError } = await admin
      .from("organizations")
      .select("id")
      .eq("id", existingProfile.org_id)
      .maybeSingle();

    if (orgReadError) {
      return {
        orgId: null,
        error: formatSupabaseError(orgReadError, "Could not read organization."),
      };
    }

    if (org) {
      return { orgId: existingProfile.org_id, method: "existing" };
    }
  }

  const { data: newOrg, error: orgInsertError } = await admin
    .from("organizations")
    .insert({ name: orgNameFromUser(user) })
    .select("id")
    .single();

  if (orgInsertError || !newOrg) {
    return {
      orgId: null,
      error: formatSupabaseError(orgInsertError, "Could not create organization."),
    };
  }

  const { error: profileUpsertError } = await admin.from("profiles").upsert(
    {
      id: user.id,
      org_id: newOrg.id,
      email: user.email ?? "",
      name: displayNameFromUser(user),
      role: "admin",
    },
    { onConflict: "id" },
  );

  if (profileUpsertError) {
    return {
      orgId: null,
      error: formatSupabaseError(profileUpsertError, "Could not create profile."),
    };
  }

  return { orgId: newOrg.id, method: "admin" };
}

async function bootstrapWithRpc(supabase: SupabaseClient): Promise<BootstrapResult> {
  const { data: orgId, error } = await supabase.rpc("ensure_user_profile");

  if (error) {
    const message = error.message ?? "Profile setup failed.";
    if (message.includes("does not exist")) {
      if (message.includes("ensure_user_profile") || message.includes("auth_org_id")) {
        return {
          orgId: null,
          error:
            "Database not fully set up. Run dashboard/supabase/bootstrap-login.sql in Supabase SQL Editor.",
        };
      }
    }
    return { orgId: null, error: formatSupabaseError(error, message) };
  }

  if (!orgId) {
    return { orgId: null, error: "Profile setup returned no organization." };
  }

  return { orgId: orgId as string, method: "rpc" };
}

export async function bootstrapUserProfile(
  user: User,
  supabase?: SupabaseClient,
): Promise<BootstrapResult> {
  const admin = createAdminClient();
  if (admin) {
    const adminResult = await bootstrapWithAdmin(user);
    if (adminResult.orgId) return adminResult;
    // Fall through to RPC if admin failed (e.g. missing tables)
  }

  if (supabase) {
    return bootstrapWithRpc(supabase);
  }

  return {
    orgId: null,
    error: admin
      ? "Could not set up workspace automatically."
      : "Add SUPABASE_SERVICE_ROLE_KEY to dashboard/.env.local, or run dashboard/supabase/fix-missing-profile.sql in Supabase SQL Editor.",
  };
}
