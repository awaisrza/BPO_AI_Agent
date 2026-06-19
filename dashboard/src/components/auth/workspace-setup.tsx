"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { LogOut, RefreshCw } from "lucide-react";
import { ProfileSetupAlert } from "@/components/auth/profile-setup-alert";
import { Button } from "@/components/ui/button";
import { createClient } from "@/lib/supabase/client";
import { getOrgId } from "@/lib/get-org-id";

export function WorkspaceSetup({ email }: { email: string }) {
  const router = useRouter();
  const [retrying, setRetrying] = useState(false);
  const [error, setError] = useState("");

  async function handleRetry() {
    setRetrying(true);
    setError("");

    try {
      const supabase = createClient();
      await getOrgId(supabase);
      window.location.assign("/");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Setup still incomplete. Confirm the SQL ran with Success in Supabase.",
      );
      setRetrying(false);
    }
  }

  async function handleSignOut() {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/login");
    router.refresh();
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface px-4 py-10">
      <div className="w-full max-w-2xl space-y-6">
        <div className="text-center">
          <p className="data-label">AI Fronter</p>
          <h1 className="mt-2 text-2xl font-semibold text-foreground">Finish workspace setup</h1>
          <p className="mt-2 text-body text-foreground-muted">
            Signed in as <span className="text-foreground">{email}</span>. One SQL script in Supabase
            unlocks the dashboard.
          </p>
        </div>

        <ProfileSetupAlert />

        {error && (
          <p className="rounded-lg border border-status-danger/30 bg-status-danger-muted px-4 py-3 text-sm text-status-danger">
            {error}
          </p>
        )}

        <div className="flex flex-wrap justify-center gap-3">
          <Button onClick={handleRetry} disabled={retrying}>
            <RefreshCw className={`h-4 w-4 ${retrying ? "animate-spin" : ""}`} />
            {retrying ? "Checking…" : "Continue after running SQL"}
          </Button>
          <Button variant="secondary" onClick={handleSignOut}>
            <LogOut className="h-4 w-4" />
            Sign out
          </Button>
        </div>
      </div>
    </div>
  );
}
