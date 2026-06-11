"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Mic, Play, Save } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/input";
import { createClient, isSupabaseConfigured } from "@/lib/supabase/client";
import type { CampaignRow, ScriptJson } from "@/lib/types/database";

export function CampaignEditorForm({ id }: { id: string }) {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [title, setTitle] = useState("Campaign script");
  const [greeting, setGreeting] = useState("");
  const [pitch, setPitch] = useState("");
  const [questions, setQuestions] = useState<string[]>([]);
  const [transferPreset, setTransferPreset] = useState("closers-01");
  const [transferLine, setTransferLine] = useState("");
  const [notInterestedLine, setNotInterestedLine] = useState("");
  const [botCount, setBotCount] = useState(0);
  const [vicidialId, setVicidialId] = useState("—");

  useEffect(() => {
    async function load() {
      if (!isSupabaseConfigured()) {
        setError("Add Supabase keys to .env.local and restart the dev server.");
        setLoading(false);
        return;
      }

      try {
        const supabase = createClient();
        const { data: campaign, error: campaignError } = await supabase
          .from("campaigns")
          .select("id, name, script_json, vicidial_campaign_id")
          .eq("id", id)
          .single();

        if (campaignError) throw campaignError;

        const row = campaign as CampaignRow;
        const script = row.script_json as ScriptJson;

        setTitle(script.label ?? row.name);
        setGreeting(script.greeting);
        setPitch(script.pitch);
        setQuestions(script.qualifying_questions ?? []);
        setTransferLine(script.transfer_line);
        setNotInterestedLine(script.not_interested_line);
        setTransferPreset(script.transfer_preset ?? "closers-01");
        setVicidialId(row.vicidial_campaign_id ?? "—");

        const { count } = await supabase
          .from("bots")
          .select("*", { count: "exact", head: true })
          .eq("campaign_id", id);

        setBotCount(count ?? 0);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load campaign.");
      } finally {
        setLoading(false);
      }
    }

    load();
  }, [id]);

  async function handleSave() {
    setSaving(true);
    setError("");
    setSaved(false);

    try {
      const supabase = createClient();
      const script_json: ScriptJson = {
        label: title,
        greeting,
        pitch,
        qualifying_questions: questions,
        transfer_line: transferLine,
        not_interested_line: notInterestedLine,
        transfer_preset: transferPreset,
      };

      const { error: updateError } = await supabase
        .from("campaigns")
        .update({ script_json })
        .eq("id", id);

      if (updateError) throw updateError;

      setSaved(true);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save campaign.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <p className="text-sm text-zinc-500">Loading campaign…</p>;
  }

  if (error && !greeting) {
    return (
      <p className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
        {error}
      </p>
    );
  }

  return (
    <>
      <PageHeader
        title={title}
        description="Configure what the bot says, qualifying questions, and transfer rules."
        action={
          <>
            <Button variant="secondary">
              <Play className="h-4 w-4" />
              Test bot
            </Button>
            <Button onClick={handleSave} disabled={saving}>
              <Save className="h-4 w-4" />
              {saving ? "Saving…" : saved ? "Saved" : "Save"}
            </Button>
          </>
        }
      />

      {error && (
        <p className="mb-6 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {error}
        </p>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader
              title="Opening script"
              description="Played when a human answers"
              action={<Badge variant="success">Cached audio</Badge>}
            />
            <CardBody>
              <Textarea
                className="min-h-[100px]"
                value={greeting}
                onChange={(e) => setGreeting(e.target.value)}
              />
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Pitch" description="Delivered after the caller responds to the greeting" />
            <CardBody>
              <Textarea
                className="min-h-[100px]"
                value={pitch}
                onChange={(e) => setPitch(e.target.value)}
              />
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Qualifying questions" />
            <CardBody className="space-y-2">
              {questions.map((q, index) => (
                <div
                  key={`${index}-${q}`}
                  className="flex items-center gap-3 rounded-lg border border-surface-border bg-surface-overlay/40 px-4 py-3"
                >
                  <input type="checkbox" defaultChecked className="rounded accent-zinc-100" />
                  <span className="text-sm text-zinc-300">{q}</span>
                </div>
              ))}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Transfer lines" />
            <CardBody className="space-y-4">
              <div>
                <p className="mb-2 text-xs text-zinc-600">Transfer line (qualified)</p>
                <Textarea value={transferLine} onChange={(e) => setTransferLine(e.target.value)} />
              </div>
              <div>
                <p className="mb-2 text-xs text-zinc-600">Not interested line</p>
                <Textarea
                  value={notInterestedLine}
                  onChange={(e) => setNotInterestedLine(e.target.value)}
                />
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Transfer rule" />
            <CardBody>
              <p className="rounded-lg bg-emerald-500/[0.06] px-4 py-3 text-sm text-emerald-400/90">
                IF qualified AND interested → Warm transfer to{" "}
                <span className="font-mono text-emerald-300">{transferPreset}</span>
              </p>
            </CardBody>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader title="Settings" />
            <CardBody className="space-y-5">
              <SettingRow label="Voice" value="Sarah · US English" icon={Mic} />
              <SettingRow label="ViciDial ID" value={vicidialId} mono />
              <SettingRow label="Bots assigned" value={`${botCount} bots`} />
              <SettingRow label="Transfer queue" value={transferPreset} mono />
            </CardBody>
          </Card>
        </div>
      </div>
    </>
  );
}

function SettingRow({
  label,
  value,
  mono,
  icon: Icon,
}: {
  label: string;
  value: string;
  mono?: boolean;
  icon?: LucideIcon;
}) {
  return (
    <div>
      <p className="text-xs text-zinc-600">{label}</p>
      <p className={`mt-1.5 flex items-center gap-2 text-sm text-zinc-200 ${mono ? "font-mono" : ""}`}>
        {Icon && <Icon className="h-3.5 w-3.5 text-zinc-600" />}
        {value}
      </p>
    </div>
  );
}
