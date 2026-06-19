"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Mic, Pause, Play, Plus, RefreshCw, Save, Trash2 } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Textarea, Input, Select, Field } from "@/components/ui/input";
import type { VicidialCloser } from "@/lib/vicidial/closers";
import { createClient, isSupabaseConfigured, supabaseConfigHelp } from "@/lib/supabase/client";
import type { CampaignRow, CampaignStatus, KnowledgeEntry, ScriptJson } from "@/lib/types/database";
import { setCampaignRunningStatus } from "@/lib/campaigns";
import { DEFAULT_KNOWLEDGE_BASE } from "@/lib/types/database";

export function CampaignEditorForm({ id }: { id: string }) {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [togglingStatus, setTogglingStatus] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [campaignStatus, setCampaignStatus] = useState<CampaignStatus>("paused");
  const [campaignName, setCampaignName] = useState("");
  const [scriptLabel, setScriptLabel] = useState("");
  const [greeting, setGreeting] = useState("");
  const [pitch, setPitch] = useState("");
  const [questions, setQuestions] = useState<string[]>([]);
  const [transferPreset, setTransferPreset] = useState("closers-01");
  const [transferCloserUser, setTransferCloserUser] = useState("");
  const [transferCloserName, setTransferCloserName] = useState("");
  const [closers, setClosers] = useState<VicidialCloser[]>([]);
  const [closersLoading, setClosersLoading] = useState(false);
  const [closersError, setClosersError] = useState("");
  const [transferLine, setTransferLine] = useState("");
  const [notInterestedLine, setNotInterestedLine] = useState("");
  const [botCount, setBotCount] = useState(0);
  const [vicidialId, setVicidialId] = useState("—");
  const [knowledge, setKnowledge] = useState<KnowledgeDraft[]>([]);

  useEffect(() => {
    async function load() {
      if (!isSupabaseConfigured()) {
        setError(supabaseConfigHelp());
        setLoading(false);
        return;
      }

      try {
        const supabase = createClient();
        const { data: campaign, error: campaignError } = await supabase
          .from("campaigns")
          .select("id, name, status, script_json, vicidial_campaign_id")
          .eq("id", id)
          .single();

        if (campaignError) throw campaignError;

        const row = campaign as CampaignRow;
        const script = row.script_json as ScriptJson;

        setCampaignName(row.name);
        setCampaignStatus(row.status);
        setScriptLabel(script.label ?? `${row.name} v1`);
        setGreeting(script.greeting);
        setPitch(script.pitch);
        setQuestions(script.qualifying_questions ?? []);
        setTransferLine(script.transfer_line);
        setNotInterestedLine(script.not_interested_line);
        setTransferPreset(script.transfer_preset ?? "closers-01");
        setTransferCloserUser(script.transfer_closer_user ?? "");
        setTransferCloserName(script.transfer_closer_name ?? "");
        setVicidialId(row.vicidial_campaign_id ?? "—");
        setKnowledge(
          (script.knowledge_base?.length ? script.knowledge_base : DEFAULT_KNOWLEDGE_BASE).map(
            toKnowledgeDraft,
          ),
        );

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
    void loadClosers();
  }, [id]);

  async function loadClosers() {
    setClosersLoading(true);
    setClosersError("");

    try {
      const res = await fetch(`/api/vicidial/closers?campaignId=${encodeURIComponent(id)}`);
      const data = (await res.json()) as {
        closers?: VicidialCloser[];
        error?: string;
      };

      if (!res.ok) {
        setClosers(data.closers ?? []);
        setClosersError(data.error ?? "Could not load closers.");
        return;
      }

      setClosers(data.closers ?? []);
    } catch {
      setClosersError("Could not reach ViciDial. Check Integrations settings.");
    } finally {
      setClosersLoading(false);
    }
  }

  function handleCloserChange(userId: string) {
    setTransferCloserUser(userId);
    const closer = closers.find((c) => c.user === userId);
    setTransferCloserName(closer?.fullName ?? "");
    setSaved(false);
  }

  function addQuestion() {
    setQuestions((prev) => [...prev, ""]);
    setSaved(false);
  }

  function updateQuestion(index: number, value: string) {
    setQuestions((prev) => prev.map((q, i) => (i === index ? value : q)));
    setSaved(false);
  }

  function removeQuestion(index: number) {
    setQuestions((prev) => prev.filter((_, i) => i !== index));
    setSaved(false);
  }

  function addKnowledgeEntry() {
    setKnowledge((prev) => [...prev, emptyKnowledgeDraft()]);
    setSaved(false);
  }

  function updateKnowledge(index: number, patch: Partial<KnowledgeDraft>) {
    setKnowledge((prev) => prev.map((entry, i) => (i === index ? { ...entry, ...patch } : entry)));
    setSaved(false);
  }

  function removeKnowledgeEntry(index: number) {
    setKnowledge((prev) => prev.filter((_, i) => i !== index));
    setSaved(false);
  }

  async function toggleCampaignStatus() {
    setTogglingStatus(true);
    setError("");

    try {
      const supabase = createClient();
      const nextStatus: CampaignStatus = campaignStatus === "running" ? "paused" : "running";
      await setCampaignRunningStatus(supabase, id, nextStatus);

      setCampaignStatus(nextStatus);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update campaign status.");
    } finally {
      setTogglingStatus(false);
    }
  }

  async function handleSave() {
    setSaving(true);
    setError("");
    setSaved(false);

    try {
      const supabase = createClient();
      const trimmedName = campaignName.trim();
      if (!trimmedName) {
        throw new Error("Campaign name is required.");
      }

      const script_json: ScriptJson = {
        label: scriptLabel.trim() || `${trimmedName} v1`,
        greeting,
        pitch,
        qualifying_questions: questions.map((q) => q.trim()).filter(Boolean),
        transfer_line: transferLine,
        not_interested_line: notInterestedLine,
        transfer_preset: transferPreset,
        transfer_closer_user: transferCloserUser || null,
        transfer_closer_name: transferCloserName || null,
        knowledge_base: knowledge.map(fromKnowledgeDraft).filter((entry) => entry.answer),
      };

      const { error: updateError } = await supabase
        .from("campaigns")
        .update({ name: trimmedName, script_json })
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
    return <p className="text-sm text-foreground-muted">Loading campaign…</p>;
  }

  if (error && !greeting) {
    return (
      <p className="rounded-lg border border-status-danger/30 bg-status-danger-muted px-4 py-3 text-sm text-status-danger">
        {error}
      </p>
    );
  }

  return (
    <>
      <PageHeader
        title={campaignName || "Campaign"}
        description="Configure what the bot says, qualifying questions, and transfer rules."
        action={
          <>
            <Badge variant={campaignStatus === "running" ? "live" : "default"} dot={campaignStatus === "running"}>
              {campaignStatus === "running" ? "Running" : "Paused"}
            </Badge>
            {campaignStatus === "running" ? (
              <Button variant="secondary" onClick={toggleCampaignStatus} disabled={togglingStatus}>
                <Pause className="h-4 w-4" />
                {togglingStatus ? "Pausing…" : "Pause campaign"}
              </Button>
            ) : (
              <Button onClick={toggleCampaignStatus} disabled={togglingStatus || botCount === 0}>
                <Play className="h-4 w-4" />
                {togglingStatus ? "Starting…" : "Run campaign"}
              </Button>
            )}
            <Button variant="secondary" onClick={handleSave} disabled={saving || !campaignName.trim()}>
              <Save className="h-4 w-4" />
              {saving ? "Saving…" : saved ? "Saved" : "Save"}
            </Button>
          </>
        }
      />

      {campaignStatus === "paused" && botCount > 0 && (
        <p className="mb-6 rounded-lg border border-border bg-surface-raised px-4 py-3 text-sm text-foreground-muted">
          Campaign is paused. Click <strong className="text-foreground">Run campaign</strong> to start all{" "}
          {botCount} assigned agent{botCount === 1 ? "" : "s"}.
        </p>
      )}

      {error && (
        <p className="mb-6 rounded-lg border border-status-danger/30 bg-status-danger-muted px-4 py-3 text-sm text-status-danger">
          {error}
        </p>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader
              title="Campaign details"
              description="Shown in the dashboard and when assigning bots."
            />
            <CardBody className="grid gap-4 sm:grid-cols-2">
              <Field label="Campaign name" description="Name on the campaigns list.">
                <Input
                  value={campaignName}
                  onChange={(e) => {
                    setCampaignName(e.target.value);
                    setSaved(false);
                  }}
                  placeholder="e.g. Medicare AEP"
                  required
                />
              </Field>
              <Field label="Script name" description="Version label for this script.">
                <Input
                  value={scriptLabel}
                  onChange={(e) => {
                    setScriptLabel(e.target.value);
                    setSaved(false);
                  }}
                  placeholder="e.g. Medicare AEP v2"
                />
              </Field>
            </CardBody>
          </Card>

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
            <CardHeader
              title="Qualifying questions"
              description="Asked one at a time after the pitch. Caller needs mostly positive answers to transfer."
              action={
                <Button type="button" variant="secondary" size="sm" onClick={addQuestion}>
                  <Plus className="h-3.5 w-3.5" />
                  Add question
                </Button>
              }
            />
            <CardBody className="space-y-3">
              {questions.length === 0 ? (
                <p className="rounded-lg border border-dashed border-surface-border px-4 py-6 text-center text-sm text-foreground-muted">
                  No qualifying questions yet.{" "}
                  <button
                    type="button"
                    onClick={addQuestion}
                    className="text-foreground-secondary underline hover:text-white"
                  >
                    Add your first question
                  </button>
                </p>
              ) : (
                questions.map((q, index) => (
                  <div
                    key={`q-${index}`}
                    className="flex items-start gap-3 rounded-lg border border-surface-border bg-surface-overlay/40 px-4 py-3"
                  >
                    <span className="mt-2 shrink-0 font-mono text-xs text-foreground-faint">
                      Q{index + 1}
                    </span>
                    <Input
                      value={q}
                      onChange={(e) => updateQuestion(index, e.target.value)}
                      placeholder="e.g. Do you currently have Medicare Part A and B?"
                      className="flex-1 border-transparent bg-transparent px-0 focus:border-surface-border focus:bg-surface-overlay"
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => removeQuestion(index)}
                      aria-label={`Remove question ${index + 1}`}
                      className="shrink-0 text-foreground-muted hover:text-status-danger"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                ))
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="Knowledge base"
              description="Exact answers for common caller questions. Unmatched questions use AI (Gemini) with these facts only."
              action={
                <Button type="button" variant="secondary" size="sm" onClick={addKnowledgeEntry}>
                  <Plus className="h-3.5 w-3.5" />
                  Add topic
                </Button>
              }
            />
            <CardBody className="space-y-4">
              {knowledge.length === 0 ? (
                <p className="rounded-lg border border-dashed border-surface-border px-4 py-6 text-center text-sm text-foreground-muted">
                  No knowledge entries yet.{" "}
                  <button
                    type="button"
                    onClick={addKnowledgeEntry}
                    className="text-foreground-secondary underline hover:text-white"
                  >
                    Add your first topic
                  </button>
                </p>
              ) : (
                knowledge.map((entry, index) => (
                  <div
                    key={`kb-${index}`}
                    className="space-y-3 rounded-lg border border-surface-border bg-surface-overlay/40 px-4 py-4"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <p className="text-xs font-medium text-foreground-muted">Topic {index + 1}</p>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => removeKnowledgeEntry(index)}
                        aria-label={`Remove knowledge topic ${index + 1}`}
                        className="shrink-0 text-foreground-muted hover:text-status-danger"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                    <Field label="Topic label" description="What this answer is about (for your team).">
                      <Input
                        value={entry.topic}
                        onChange={(e) => updateKnowledge(index, { topic: e.target.value })}
                        placeholder="e.g. Who is calling?"
                      />
                    </Field>
                    <Field
                      label="Trigger phrases"
                      description="Comma-separated words callers might say. Bot matches these first."
                    >
                      <Input
                        value={entry.triggersText}
                        onChange={(e) => updateKnowledge(index, { triggersText: e.target.value })}
                        placeholder="who are you, who's this, spam call"
                      />
                    </Field>
                    <Field label="Bot answer" description="Exact line the bot says when matched.">
                      <Textarea
                        className="min-h-[80px]"
                        value={entry.answer}
                        onChange={(e) => updateKnowledge(index, { answer: e.target.value })}
                        placeholder="This is Sarah from ABC Benefits on a recorded line."
                      />
                    </Field>
                  </div>
                ))
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="Assign closer"
              description="Qualified leads transfer to this closer. List shows agents logged into ViciDial right now."
              action={
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => void loadClosers()}
                  disabled={closersLoading}
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${closersLoading ? "animate-spin" : ""}`} />
                  Refresh
                </Button>
              }
            />
            <CardBody className="space-y-4">
              <Field
                label="Closer"
                description="Pick who receives warm transfers when this campaign runs."
              >
                <Select
                  className="w-full"
                  value={transferCloserUser}
                  onChange={(e) => handleCloserChange(e.target.value)}
                >
                  <option value="">
                    {closersLoading ? "Loading closers…" : "Select a closer"}
                  </option>
                  {closers.map((closer) => (
                    <option key={closer.user} value={closer.user}>
                      {closer.fullName}
                      {closer.available ? " · Available" : " · On a call"}
                    </option>
                  ))}
                </Select>
              </Field>

              {closersError && (
                <p className="rounded-md border border-status-warning/30 bg-status-warning-muted px-4 py-3 text-body text-status-warning">
                  {closersError}
                </p>
              )}

              {!closersLoading && !closersError && closers.length === 0 && (
                <p className="text-sm text-foreground-muted">
                  No closers logged in right now. Ask your closers to log into ViciDial, then click
                  Refresh.
                </p>
              )}

              {transferCloserUser && (
                <p className="rounded-md bg-brand-muted px-4 py-3 text-body text-brand">
                  IF qualified → Warm transfer to{" "}
                  <span className="font-medium text-foreground">
                    {transferCloserName || transferCloserUser}
                  </span>
                </p>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Transfer lines" />
            <CardBody className="space-y-4">
              <div>
                <p className="mb-2 text-xs text-foreground-faint">Transfer line (qualified)</p>
                <Textarea value={transferLine} onChange={(e) => setTransferLine(e.target.value)} />
              </div>
              <div>
                <p className="mb-2 text-xs text-foreground-faint">Not interested line</p>
                <Textarea
                  value={notInterestedLine}
                  onChange={(e) => setNotInterestedLine(e.target.value)}
                />
              </div>
            </CardBody>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader title="Settings" />
            <CardBody className="space-y-5">
              <SettingRow label="Campaign" value={campaignName || "—"} />
              <SettingRow label="Script" value={scriptLabel || "—"} />
              <SettingRow label="Voice" value="Sarah · US English" icon={Mic} />
              <SettingRow label="ViciDial ID" value={vicidialId} mono />
              <SettingRow
                label="Status"
                value={campaignStatus === "running" ? "Running — agents can go live" : "Paused"}
              />
              <SettingRow label="Bots assigned" value={`${botCount} bots`} />
              <SettingRow
                label="Assigned closer"
                value={transferCloserName || transferCloserUser || "Not selected"}
              />
              <SettingRow
                label="Knowledge topics"
                value={`${knowledge.filter((k) => k.answer.trim()).length} topics`}
              />
            </CardBody>
          </Card>
        </div>
      </div>
    </>
  );
}

type KnowledgeDraft = {
  topic: string;
  triggersText: string;
  answer: string;
};

function emptyKnowledgeDraft(): KnowledgeDraft {
  return { topic: "", triggersText: "", answer: "" };
}

function toKnowledgeDraft(entry: KnowledgeEntry): KnowledgeDraft {
  return {
    topic: entry.topic,
    triggersText: entry.triggers.join(", "),
    answer: entry.answer,
  };
}

function fromKnowledgeDraft(draft: KnowledgeDraft): KnowledgeEntry {
  return {
    topic: draft.topic.trim(),
    triggers: draft.triggersText
      .split(",")
      .map((part) => part.trim())
      .filter(Boolean),
    answer: draft.answer.trim(),
  };
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
      <p className="text-xs text-foreground-faint">{label}</p>
      <p className={`mt-1.5 flex items-center gap-2 text-sm text-zinc-200 ${mono ? "font-mono" : ""}`}>
        {Icon && <Icon className="h-3.5 w-3.5 text-foreground-faint" />}
        {value}
      </p>
    </div>
  );
}
