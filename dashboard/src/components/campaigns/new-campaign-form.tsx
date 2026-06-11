"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/input";
import { createClient, isSupabaseConfigured } from "@/lib/supabase/client";
import { buildNewCampaignPayload } from "@/lib/campaigns";
import { formatSupabaseError } from "@/lib/errors";
import { getOrgId } from "@/lib/get-org-id";
import type { CampaignStatus } from "@/lib/types/database";

export function NewCampaignForm() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [script, setScript] = useState("");
  const [status, setStatus] = useState<CampaignStatus>("paused");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    if (!isSupabaseConfigured()) {
      setError("Add Supabase keys to .env.local and restart the dev server.");
      return;
    }

    setSubmitting(true);

    try {
      const supabase = createClient();
      const orgId = await getOrgId(supabase);

      const { data: campaign, error: insertError } = await supabase
        .from("campaigns")
        .insert(
          buildNewCampaignPayload({
            orgId,
            name,
            scriptLabel: script || undefined,
            status,
          }),
        )
        .select("id")
        .single();

      if (insertError) {
        throw new Error(formatSupabaseError(insertError, "Could not create campaign."));
      }
      if (!campaign?.id) {
        throw new Error("Campaign was not created.");
      }

      router.push(`/campaigns/${campaign.id}`);
      router.refresh();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : formatSupabaseError(err, "Could not create campaign."),
      );
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="max-w-lg space-y-6">
      <Field
        label="Campaign name"
        description="Shown in the dashboard and assigned to bots."
      >
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Medicare AEP"
          required
          autoFocus
        />
      </Field>

      <Field
        label="Script name"
        description="Optional label for the script version."
      >
        <Input
          value={script}
          onChange={(e) => setScript(e.target.value)}
          placeholder="e.g. Medicare AEP v2"
        />
      </Field>

      <Field label="Status" description="New campaigns start paused until you assign bots.">
        <Select
          value={status}
          onChange={(e) => setStatus(e.target.value as CampaignStatus)}
        >
          <option value="paused">Paused</option>
          <option value="running">Running</option>
        </Select>
      </Field>

      {error && (
        <p className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {error}
        </p>
      )}

      <div className="flex gap-3">
        <Button type="submit" disabled={submitting || !name.trim()}>
          {submitting ? "Creating…" : "Create campaign"}
        </Button>
        <Button
          type="button"
          variant="secondary"
          onClick={() => router.push("/campaigns")}
        >
          Cancel
        </Button>
      </div>
    </form>
  );
}
