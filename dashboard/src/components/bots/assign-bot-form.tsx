"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/input";
import { createClient, isSupabaseConfigured, supabaseConfigHelp } from "@/lib/supabase/client";
import { formatSupabaseError } from "@/lib/errors";
import { getOrgId } from "@/lib/get-org-id";

type CampaignOption = { id: string; name: string };

export function AssignBotForm() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [campaignId, setCampaignId] = useState("");
  const [campaigns, setCampaigns] = useState<CampaignOption[]>([]);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!isSupabaseConfigured()) return;

    async function load() {
      const supabase = createClient();
      const [{ data: campaignRows }, { count }] = await Promise.all([
        supabase.from("campaigns").select("id, name").order("name"),
        supabase.from("bots").select("*", { count: "exact", head: true }),
      ]);

      setCampaigns(campaignRows ?? []);
      if (campaignRows?.[0]) setCampaignId(campaignRows[0].id);
      setName(`Bot-${String((count ?? 0) + 1).padStart(2, "0")}`);
    }

    load();
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    if (!campaignId) {
      setError("Create a campaign first, then assign a bot to it.");
      return;
    }

    if (!isSupabaseConfigured()) {
      setError(supabaseConfigHelp());
      return;
    }

    setSubmitting(true);

    try {
      const supabase = createClient();
      const orgId = await getOrgId(supabase);

      const { error: insertError } = await supabase.from("bots").insert({
        org_id: orgId,
        name: name.trim(),
        campaign_id: campaignId,
        status: "offline",
      });

      if (insertError) {
        throw new Error(formatSupabaseError(insertError, "Could not assign bot."));
      }

      router.push("/bots");
      router.refresh();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : formatSupabaseError(err, "Could not assign bot."),
      );
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="max-w-lg space-y-6">
      <Field label="Bot name" description="Shown in the dashboard and ViciDial agent seat.">
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Bot-01"
          required
          autoFocus
        />
      </Field>

      <Field label="Campaign" description="Which outbound campaign this bot dials for.">
        {campaigns.length === 0 ? (
          <p className="text-sm text-zinc-500">
            No campaigns yet.{" "}
            <Link href="/campaigns/new" className="text-zinc-300 underline hover:text-white">
              Create one first
            </Link>
            .
          </p>
        ) : (
          <Select
            className="w-full"
            value={campaignId}
            onChange={(e) => setCampaignId(e.target.value)}
            required
          >
            {campaigns.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
        )}
      </Field>

      {error && (
        <p className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {error}
        </p>
      )}

      <div className="flex gap-3">
        <Button type="submit" disabled={submitting || !name.trim() || campaigns.length === 0}>
          {submitting ? "Assigning…" : "Assign bot"}
        </Button>
        <Button type="button" variant="secondary" onClick={() => router.push("/bots")}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
