"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  BookOpen,
  FileText,
  Megaphone,
  Pause,
  PhoneCall,
  Play,
  Plus,
  RefreshCw,
  Save,
  Settings2,
  Trash2,
  UserRound,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea, Input, Select, Field } from "@/components/ui/input";
import type { VicidialCampaignOption } from "@/lib/vicidial/campaigns";
import { normalizeVicidialCampaignId } from "@/lib/vicidial/campaigns";
import type { VicidialCloser } from "@/lib/vicidial/closers";
import { createClient, isSupabaseConfigured, supabaseConfigHelp } from "@/lib/supabase/client";
import type { CampaignRow, CampaignStatus, KnowledgeEntry, ScriptJson } from "@/lib/types/database";
import { DEFAULT_KNOWLEDGE_BASE } from "@/lib/types/database";
import { readJsonResponse } from "@/lib/fetch-json";
import { formatSupabaseError } from "@/lib/errors";
import { cn } from "@/lib/utils";

type EditorSection =
  | "details"
  | "script"
  | "knowledge"
  | "transfer"
  | "test"
  | "overview";

const EDITOR_SECTIONS: {
  id: EditorSection;
  label: string;
  hint: string;
  icon: LucideIcon;
  dot: string;
}[] = [
  {
    id: "details",
    label: "Details",
    hint: "Name · ViciDial ID",
    icon: Megaphone,
    dot: "bg-brand",
  },
  {
    id: "script",
    label: "Script",
    hint: "Greeting · pitch · Qs",
    icon: FileText,
    dot: "bg-status-info",
  },
  {
    id: "knowledge",
    label: "Knowledge",
    hint: "FAQ answers",
    icon: BookOpen,
    dot: "bg-status-success",
  },
  {
    id: "transfer",
    label: "Transfer",
    hint: "Closer · lines",
    icon: UserRound,
    dot: "bg-status-warning",
  },
  {
    id: "test",
    label: "Test dial",
    hint: "GPU · place call",
    icon: PhoneCall,
    dot: "bg-brand",
  },
  {
    id: "overview",
    label: "Overview",
    hint: "Status snapshot",
    icon: Settings2,
    dot: "bg-foreground-faint",
  },
];

export function CampaignEditorForm({ id }: { id: string }) {
  const router = useRouter();
  const [section, setSection] = useState<EditorSection>("details");
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
  const [botAgentUsers, setBotAgentUsers] = useState<string[]>([]);
  const [transferLine, setTransferLine] = useState("");
  const [notInterestedLine, setNotInterestedLine] = useState("");
  const [botCount, setBotCount] = useState(0);
  const [vicidialCampaignId, setVicidialCampaignId] = useState("");
  const [vicidialCampaigns, setVicidialCampaigns] = useState<VicidialCampaignOption[]>([]);
  const [vicidialCampaignsLoading, setVicidialCampaignsLoading] = useState(false);
  const [vicidialCampaignsError, setVicidialCampaignsError] = useState("");
  const [readinessHint, setReadinessHint] = useState("");
  const [knowledge, setKnowledge] = useState<KnowledgeDraft[]>([]);
  const [testPhone, setTestPhone] = useState("+923142222318");
  const [testListId, setTestListId] = useState("101");
  const [testOutboundCid, setTestOutboundCid] = useState("+19482194316");
  const [testDialing, setTestDialing] = useState(false);
  const [testDialResult, setTestDialResult] = useState("");
  const [testDialProgress, setTestDialProgress] = useState<string[]>([]);
  const [runProgress, setRunProgress] = useState<string[]>([]);

  // While Running, poll the dialer — when every lead is dialed, auto-pause (Pause → Run).
  useEffect(() => {
    if (campaignStatus !== "running" || togglingStatus) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const res = await fetch(`/api/campaigns/${id}/dialing-status`, { cache: "no-store" });
        const data = await readJsonResponse<{
          done?: boolean;
          autoPaused?: boolean;
          status?: CampaignStatus;
          message?: string;
          detail?: string;
          error?: string;
        }>(res);
        if (cancelled || !res.ok) return;
        if (data.autoPaused || (data.done && data.status === "paused")) {
          setCampaignStatus("paused");
          setReadinessHint(
            data.message ??
              "All leads dialed — campaign paused. Reset leads to NEW on the Leads page to run again.",
          );
          setRunProgress((prev) => [
            ...prev,
            `✓ dialing finished: ${data.detail ?? "hopper empty"}`,
          ]);
          router.refresh();
        }
      } catch {
        /* ignore transient poll errors */
      }
    };
    void tick();
    const timer = setInterval(() => void tick(), 15_000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [campaignStatus, togglingStatus, id, router]);

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
        if (!campaign) {
          throw new Error(
            "Campaign not found for this account. Go back to Campaigns and open one from the list, or create a new campaign.",
          );
        }

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
        setVicidialCampaignId(
          row.vicidial_campaign_id ? normalizeVicidialCampaignId(row.vicidial_campaign_id) : "",
        );
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

        const { data: botRows } = await supabase.from("bots").select("vicidial_agent_user");
        setBotAgentUsers(
          (botRows ?? [])
            .map((b) => (b.vicidial_agent_user as string | null)?.trim() ?? "")
            .filter(Boolean),
        );
      } catch (err) {
        const code = (err as { code?: string } | null)?.code;
        if (code === "PGRST116") {
          setError(
            "Campaign not found for this account (wrong org or deleted). Open Campaigns and pick one from your list, or create a new campaign.",
          );
        } else {
          setError(formatSupabaseError(err, "Could not load campaign."));
        }
      } finally {
        setLoading(false);
      }
    }

    load();
    void loadClosers();
    void loadVicidialCampaigns();
  }, [id]);

  async function loadVicidialCampaigns() {
    setVicidialCampaignsLoading(true);
    setVicidialCampaignsError("");
    try {
      const res = await fetch("/api/vicidial/campaigns");
      const data = await readJsonResponse<{
        campaigns?: VicidialCampaignOption[];
        error?: string;
      }>(res);
      if (!res.ok) {
        setVicidialCampaignsError(data.error ?? "Could not load ViciDial campaigns.");
        return;
      }
      setVicidialCampaigns(data.campaigns ?? []);
      if (data.campaigns?.length) {
        setVicidialCampaignId((current) => {
          const normalized = normalizeVicidialCampaignId(current);
          if (normalized !== current) return normalized;
          return current;
        });
      }
    } catch {
      setVicidialCampaignsError("Could not reach ViciDial.");
    } finally {
      setVicidialCampaignsLoading(false);
    }
  }

  async function loadClosers() {
    setClosersLoading(true);
    setClosersError("");

    try {
      const res = await fetch(`/api/vicidial/closers?campaignId=${encodeURIComponent(id)}`);
      const data = await readJsonResponse<{
        closers?: VicidialCloser[];
        error?: string;
      }>(res);

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
    const name = closer?.fullName?.replace(/<[^>]+>/g, "").trim();
    setTransferCloserName(name ?? "");
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

  async function waitForGpuReady(pushProgress: (line: string) => void, progress: string[]) {
    const prewarmTimeoutMs = 900_000;
    const pollMs = 3_000;
    pushProgress("Starting GPU warmup (supervisor + prewarm)…");
    const warmStart = await fetch(`/api/campaigns/${id}/gpu-warmup`, {
      method: "POST",
    });
    const warmStartData = await readJsonResponse<{
      error?: string;
      gpuMessage?: string;
      message?: string;
      phase?: string;
      logTail?: string[];
    }>(warmStart);
    if (!warmStart.ok) {
      throw new Error(warmStartData.error ?? "Could not start GPU warmup.");
    }
    if (warmStartData.gpuMessage) pushProgress(`GPU: ${warmStartData.gpuMessage}`);
    if (warmStartData.message) pushProgress(warmStartData.message);
    warmStartData.logTail?.slice(-3).forEach((line) => pushProgress(`  log: ${line}`));

    const warmupStarted = Date.now();
    let gpuReady = false;
    while (Date.now() - warmupStarted < prewarmTimeoutMs) {
      const warmRes = await fetch(`/api/campaigns/${id}/gpu-warmup`, {
        cache: "no-store",
      });
      const warm = await readJsonResponse<{
        ready?: boolean;
        phase?: string;
        message?: string;
        logTail?: string[];
        error?: string;
      }>(warmRes);
      if (!warmRes.ok) {
        throw new Error(warm.error ?? "GPU warmup status failed.");
      }
      const elapsed = Math.round((Date.now() - warmupStarted) / 1000);
      const statusLine = `[${elapsed}s] ${warm.phase ?? "checking"} — ${warm.message ?? "…"}`;
      if (progress[progress.length - 1] !== statusLine) {
        pushProgress(statusLine);
      }
      warm.logTail?.slice(-2).forEach((line) => {
        const logLine = `  log: ${line}`;
        if (!progress.includes(logLine)) pushProgress(logLine);
      });
      if (warm.ready) {
        gpuReady = true;
        pushProgress("GPU worker ready.");
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, pollMs));
    }

    if (!gpuReady) {
      throw new Error(
        "GPU worker did not become ready in time. SSH to the GPU: pgrep -af run_supervisor; tail /tmp/fleet_worker_*.log; curl -s http://127.0.0.1:10200/health",
      );
    }
  }

  async function runTestDial() {
    setTestDialing(true);
    setError("");
    setTestDialResult("");
    setTestDialProgress([]);

    const progress: string[] = [];

    function pushProgress(line: string) {
      progress.push(line);
      setTestDialProgress([...progress]);
    }

    try {
      await waitForGpuReady(pushProgress, progress);
      pushProgress("Placing test call in ViciDial hopper…");

      const res = await fetch(`/api/campaigns/${id}/test-dial`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          phone: testPhone.trim(),
          list_id: testListId.trim() || undefined,
          outbound_cid: testOutboundCid.trim() || undefined,
          start_campaign: false,
          skip_gpu_wait: true,
          vicidial_campaign_id: normalizeVicidialCampaignId(vicidialCampaignId),
        }),
      });
      const data = await readJsonResponse<{
        error?: string;
        message?: string;
        gpuMessage?: string;
        workerHealth?: string;
        workerReady?: boolean;
        workerWaitMs?: number;
        warmupEvents?: string[];
        steps?: { step: string; ok: boolean; detail: string }[];
        hopperPreview?: string;
        campaignStarted?: boolean;
      }>(res);

      if (!res.ok) {
        throw new Error(data.error ?? data.message ?? "Test dial failed.");
      }

      const parts: string[] = [...progress];
      if (data.message) parts.push(data.message);
      if (data.gpuMessage) parts.push(`GPU: ${data.gpuMessage}`);
      if (data.workerHealth) parts.push(`Worker: ${data.workerHealth}`);
      if (data.steps?.length) {
        const stepLines = data.steps.map((s) => `${s.ok ? "✓" : "○"} ${s.step}: ${s.detail}`);
        parts.push(stepLines.join("\n"));
      }
      if (data.hopperPreview) parts.push(`Hopper:\n${data.hopperPreview}`);
      setTestDialResult(parts.filter(Boolean).join("\n\n"));

      setCampaignStatus("running");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Test dial failed.");
    } finally {
      setTestDialing(false);
    }
  }

  async function toggleCampaignStatus() {
    setTogglingStatus(true);
    setError("");
    setReadinessHint("");
    setRunProgress([]);

    const progress: string[] = [];
    function pushProgress(line: string) {
      progress.push(line);
      setRunProgress([...progress]);
    }

    try {
      const action = campaignStatus === "running" ? "stop" : "start";
      if (action === "start") {
        await waitForGpuReady(pushProgress, progress);
        pushProgress("Starting ViciDial dialing (preflight, campaign, agent, hopper)…");
      }
      const res = await fetch(`/api/campaigns/${id}/run`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action }),
      });
      const data = await readJsonResponse<{
        error?: string;
        message?: string;
        status?: CampaignStatus;
        steps?: { step: string; ok: boolean; detail: string }[];
        readiness?: { issues?: { level: string; message: string }[] };
      }>(res);

      data.steps?.forEach((s) => pushProgress(`${s.ok ? "✓" : "✗"} ${s.step}: ${s.detail}`));
      if (!res.ok) {
        throw new Error(data.error ?? data.message ?? "Could not update campaign status.");
      }

      if (data.message) setReadinessHint(data.message);
      setCampaignStatus(data.status ?? (action === "start" ? "running" : "paused"));
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

      const vdCampaignId = normalizeVicidialCampaignId(vicidialCampaignId) || null;

      const { error: updateError } = await supabase
        .from("campaigns")
        .update({
          name: trimmedName,
          script_json,
          vicidial_campaign_id: vdCampaignId,
        })
        .eq("id", id);

      if (updateError) throw updateError;

      setVicidialCampaignId(vdCampaignId ?? "");

      setSaved(true);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save campaign.");
    } finally {
      setSaving(false);
    }
  }

  const activeSection = useMemo(
    () => EDITOR_SECTIONS.find((s) => s.id === section) ?? EDITOR_SECTIONS[0],
    [section],
  );

  if (loading) {
    return (
      <div className="flex h-full min-h-0 flex-1 items-center justify-center bg-surface-raised text-body text-foreground-muted">
        Loading campaign…
      </div>
    );
  }

  if (error && !greeting) {
    return (
      <div className="flex h-full min-h-0 flex-1 flex-col items-center justify-center gap-4 bg-surface-raised px-6">
        <p className="max-w-md rounded-md border border-status-danger/30 bg-status-danger-muted px-4 py-3 text-sm text-status-danger">
          {error}
        </p>
        <Button variant="secondary" href="/campaigns">
          <ArrowLeft className="h-4 w-4" />
          Back to campaigns
        </Button>
      </div>
    );
  }

  return (
    <div className="campaign-editor-shell relative flex h-full min-h-0 flex-1 flex-col overflow-hidden bg-surface-raised">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_80%_50%_at_0%_0%,rgba(59,130,246,0.12),transparent_55%),radial-gradient(ellipse_60%_40%_at_100%_100%,rgba(15,23,42,0.85),transparent_55%)]"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.28] [background-image:linear-gradient(rgba(255,255,255,0.028)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.028)_1px,transparent_1px)] [background-size:40px_40px] [mask-image:radial-gradient(ellipse_at_center,black_40%,transparent_85%)]"
      />

      <div className="relative flex min-h-0 flex-1 flex-col lg:flex-row">
        <aside className="flex w-full shrink-0 flex-col border-b border-surface-border-subtle bg-surface/75 backdrop-blur-md lg:h-full lg:w-56 lg:border-b-0 lg:border-r">
          <div className="border-b border-surface-border-subtle px-4 py-4">
            <Link
              href="/campaigns"
              className="inline-flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-[0.14em] text-foreground-faint transition-colors hover:text-foreground-muted"
            >
              <ArrowLeft className="h-3 w-3" />
              Campaigns
            </Link>
            <h1 className="mt-2 truncate text-lg font-semibold tracking-tight text-foreground">
              {campaignName || "Campaign"}
            </h1>
            <div className="mt-2 flex items-center gap-2">
              <Badge
                variant={campaignStatus === "running" ? "live" : "default"}
                dot={campaignStatus === "running"}
              >
                {campaignStatus === "running" ? "Running" : "Paused"}
              </Badge>
              <span className="text-2xs text-foreground-faint">
                {botCount} agent{botCount === 1 ? "" : "s"}
              </span>
            </div>
          </div>

          <nav className="flex gap-1 overflow-x-auto p-2 scrollbar-thin lg:min-h-0 lg:flex-1 lg:flex-col lg:overflow-y-auto">
            {EDITOR_SECTIONS.map((item) => {
              const Icon = item.icon;
              const selected = section === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setSection(item.id)}
                  className={cn(
                    "flex shrink-0 items-center gap-2 rounded-md px-3 py-2.5 text-left transition-colors duration-150 lg:w-full",
                    selected
                      ? "bg-surface-overlay text-foreground shadow-[inset_2px_0_0_0_var(--brand)]"
                      : "text-foreground-muted hover:bg-surface-overlay/60 hover:text-foreground-secondary",
                  )}
                >
                  <span className={cn("h-2 w-2 shrink-0 rounded-full", item.dot)} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-caption font-medium">{item.label}</span>
                    <span className="mt-0.5 hidden truncate text-2xs text-foreground-faint lg:block">
                      {item.hint}
                    </span>
                  </span>
                  <Icon className="hidden h-3.5 w-3.5 shrink-0 text-foreground-faint lg:block" />
                </button>
              );
            })}
          </nav>

          <div className="mt-auto hidden space-y-2 border-t border-surface-border-subtle p-3 lg:block">
            {campaignStatus === "running" ? (
              <Button
                className="w-full"
                variant="secondary"
                size="sm"
                onClick={() => void toggleCampaignStatus()}
                disabled={togglingStatus}
              >
                <Pause className="h-3.5 w-3.5" />
                {togglingStatus ? "Pausing…" : "Pause"}
              </Button>
            ) : (
              <Button
                className="w-full"
                size="sm"
                onClick={() => void toggleCampaignStatus()}
                disabled={togglingStatus || botCount === 0}
              >
                <Play className="h-3.5 w-3.5" />
                {togglingStatus ? "Starting…" : "Run"}
              </Button>
            )}
            <Button
              className="w-full"
              variant="secondary"
              size="sm"
              onClick={() => void handleSave()}
              disabled={saving || !campaignName.trim()}
            >
              <Save className="h-3.5 w-3.5" />
              {saving ? "Saving…" : saved ? "Saved" : "Save"}
            </Button>
          </div>
        </aside>

        <section className="flex min-h-0 min-w-0 flex-1 flex-col">
          <header className="flex flex-col gap-3 border-b border-surface-border-subtle bg-surface-raised/80 px-4 py-3 backdrop-blur-md sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <p className="text-2xs font-semibold uppercase tracking-[0.12em] text-foreground-faint">
                {activeSection.hint}
              </p>
              <h2 className="mt-0.5 truncate text-base font-semibold tracking-tight text-foreground">
                {activeSection.label}
              </h2>
            </div>
            <div className="flex shrink-0 flex-wrap items-center gap-2 lg:hidden">
              {campaignStatus === "running" ? (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => void toggleCampaignStatus()}
                  disabled={togglingStatus}
                >
                  <Pause className="h-3.5 w-3.5" />
                  {togglingStatus ? "Pausing…" : "Pause"}
                </Button>
              ) : (
                <Button
                  size="sm"
                  onClick={() => void toggleCampaignStatus()}
                  disabled={togglingStatus || botCount === 0}
                >
                  <Play className="h-3.5 w-3.5" />
                  {togglingStatus ? "Starting…" : "Run"}
                </Button>
              )}
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void handleSave()}
                disabled={saving || !campaignName.trim()}
              >
                <Save className="h-3.5 w-3.5" />
                {saving ? "Saving…" : saved ? "Saved" : "Save"}
              </Button>
            </div>
            <div className="hidden shrink-0 items-center gap-2 lg:flex">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void handleSave()}
                disabled={saving || !campaignName.trim()}
              >
                <Save className="h-3.5 w-3.5" />
                {saving ? "Saving…" : saved ? "Saved" : "Save"}
              </Button>
            </div>
          </header>

          <div className="min-h-0 flex-1 overflow-y-auto scrollbar-thin">
            <div className="mx-auto w-full max-w-2xl space-y-4 px-5 py-6">
              {campaignStatus === "paused" && botCount > 0 && section === "overview" && (
                <p className="rounded-md border border-surface-border bg-surface-overlay/80 px-3 py-2 text-caption text-foreground-muted">
                  Campaign is paused. Click <span className="text-foreground">Run</span> to dial NEW
                  leads. When every number has been called, it pauses automatically.
                </p>
              )}

              {runProgress.length > 0 && (
                <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-md border border-surface-border bg-surface-overlay/80 px-3 py-2 text-2xs text-foreground-muted">
                  {runProgress.join("\n")}
                </pre>
              )}

              {readinessHint && (
                <p className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-caption text-amber-200/90">
                  {readinessHint}
                </p>
              )}

              {error && (
                <p className="rounded-md border border-status-danger/30 bg-status-danger-muted px-3 py-2 text-caption text-status-danger">
                  {error}
                </p>
              )}

              {section === "details" && (
                <div className="space-y-5">
                  <p className="text-caption text-foreground-muted">
                    Shown in the dashboard and when assigning bots.
                  </p>
                  <div className="grid gap-4 sm:grid-cols-2">
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
                  </div>
                  <Field
                    label="ViciDial campaign ID"
                    description="Must match the campaign ID in the BPO dialer (hopper / lists). Use only the ID (e.g. test_cam)."
                  >
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                      <Input
                        list="vicidial-campaign-options"
                        value={vicidialCampaignId}
                        onChange={(e) => {
                          setVicidialCampaignId(e.target.value);
                          setSaved(false);
                        }}
                        onBlur={(e) => {
                          const n = normalizeVicidialCampaignId(e.target.value);
                          if (n !== e.target.value) {
                            setVicidialCampaignId(n);
                            setSaved(false);
                          }
                        }}
                        placeholder="e.g. test_cam"
                        className="font-mono text-sm sm:flex-1"
                      />
                      {vicidialCampaigns.length > 0 ? (
                        <Select
                          value={vicidialCampaignId || ""}
                          onChange={(e) => {
                            setVicidialCampaignId(e.target.value);
                            setSaved(false);
                          }}
                          className="font-mono text-sm sm:max-w-xs"
                        >
                          <option value="">Pick campaign…</option>
                          {vicidialCampaigns.map((c) => (
                            <option key={c.id} value={c.id}>
                              {c.id}
                              {c.name !== c.id ? ` — ${c.name}` : ""}
                            </option>
                          ))}
                        </Select>
                      ) : null}
                      <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        disabled={vicidialCampaignsLoading}
                        onClick={() => void loadVicidialCampaigns()}
                      >
                        <RefreshCw
                          className={`h-3.5 w-3.5 ${vicidialCampaignsLoading ? "animate-spin" : ""}`}
                        />
                      </Button>
                    </div>
                    {vicidialCampaigns.length > 0 && (
                      <p className="mt-1.5 text-xs text-foreground-muted">
                        {vicidialCampaigns.length} campaign(s) from ViciDial — choose from the list
                        or type the ID, then Save.
                      </p>
                    )}
                    {vicidialCampaignsError && (
                      <p className="mt-1.5 text-xs text-status-danger">{vicidialCampaignsError}</p>
                    )}
                    <datalist id="vicidial-campaign-options">
                      {vicidialCampaigns.map((c) => (
                        <option key={c.id} value={c.id} />
                      ))}
                    </datalist>
                  </Field>
                </div>
              )}

              {section === "script" && (
                <div className="space-y-6">
                  <div className="space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <p className="text-caption font-medium text-foreground-secondary">
                          Opening script
                        </p>
                        <p className="text-2xs text-foreground-faint">Played when a human answers</p>
                      </div>
                      <Badge variant="success">Cached audio</Badge>
                    </div>
                    <Textarea
                      className="min-h-[100px]"
                      value={greeting}
                      onChange={(e) => {
                        setGreeting(e.target.value);
                        setSaved(false);
                      }}
                    />
                  </div>

                  <div className="space-y-2">
                    <p className="text-caption font-medium text-foreground-secondary">Pitch</p>
                    <p className="text-2xs text-foreground-faint">
                      Delivered after the caller responds to the greeting
                    </p>
                    <Textarea
                      className="min-h-[100px]"
                      value={pitch}
                      onChange={(e) => {
                        setPitch(e.target.value);
                        setSaved(false);
                      }}
                    />
                  </div>

                  <div className="space-y-3">
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <p className="text-caption font-medium text-foreground-secondary">
                          Qualifying questions
                        </p>
                        <p className="text-2xs text-foreground-faint">
                          Asked one at a time after the pitch
                        </p>
                      </div>
                      <Button type="button" variant="secondary" size="sm" onClick={addQuestion}>
                        <Plus className="h-3.5 w-3.5" />
                        Add
                      </Button>
                    </div>
                    {questions.length === 0 ? (
                      <p className="rounded-md border border-dashed border-surface-border px-4 py-6 text-center text-sm text-foreground-muted">
                        No qualifying questions yet.{" "}
                        <button
                          type="button"
                          onClick={addQuestion}
                          className="text-foreground-secondary underline hover:text-foreground"
                        >
                          Add your first question
                        </button>
                      </p>
                    ) : (
                      questions.map((q, index) => (
                        <div
                          key={`q-${index}`}
                          className="flex items-start gap-3 rounded-md border border-surface-border bg-surface-overlay/40 px-3 py-2.5"
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
                  </div>
                </div>
              )}

              {section === "knowledge" && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-caption text-foreground-muted">
                      Exact answers for common questions. Unmatched use Gemini with these facts
                      only.
                    </p>
                    <Button type="button" variant="secondary" size="sm" onClick={addKnowledgeEntry}>
                      <Plus className="h-3.5 w-3.5" />
                      Add
                    </Button>
                  </div>
                  {knowledge.length === 0 ? (
                    <p className="rounded-md border border-dashed border-surface-border px-4 py-6 text-center text-sm text-foreground-muted">
                      No knowledge entries yet.{" "}
                      <button
                        type="button"
                        onClick={addKnowledgeEntry}
                        className="text-foreground-secondary underline hover:text-foreground"
                      >
                        Add your first topic
                      </button>
                    </p>
                  ) : (
                    knowledge.map((entry, index) => (
                      <div
                        key={`kb-${index}`}
                        className="space-y-3 rounded-md border border-surface-border bg-surface-overlay/40 px-4 py-4"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <p className="text-xs font-medium text-foreground-muted">
                            Topic {index + 1}
                          </p>
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
                        <Field label="Topic label" description="What this answer is about.">
                          <Input
                            value={entry.topic}
                            onChange={(e) => updateKnowledge(index, { topic: e.target.value })}
                            placeholder="e.g. Who is calling?"
                          />
                        </Field>
                        <Field
                          label="Trigger phrases"
                          description="Comma-separated words callers might say."
                        >
                          <Input
                            value={entry.triggersText}
                            onChange={(e) =>
                              updateKnowledge(index, { triggersText: e.target.value })
                            }
                            placeholder="who are you, who's this, spam call"
                          />
                        </Field>
                        <Field label="Bot answer" description="Exact line when matched.">
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
                </div>
              )}

              {section === "transfer" && (
                <div className="space-y-6">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-caption text-foreground-muted">
                      Qualified leads transfer to this closer (agents logged into ViciDial now).
                    </p>
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      onClick={() => void loadClosers()}
                      disabled={closersLoading}
                    >
                      <RefreshCw
                        className={`h-3.5 w-3.5 ${closersLoading ? "animate-spin" : ""}`}
                      />
                      Refresh
                    </Button>
                  </div>

                  <Field label="Closer" description="Who receives warm transfers.">
                    <Select
                      className="w-full"
                      value={transferCloserUser}
                      onChange={(e) => handleCloserChange(e.target.value)}
                    >
                      <option value="">
                        {closersLoading ? "Loading closers…" : "Select a closer"}
                      </option>
                      {closers
                        .filter((closer) => !botAgentUsers.includes(closer.user))
                        .map((closer) => (
                          <option key={closer.user} value={closer.user}>
                            {closer.fullName}
                            {closer.available ? " · Available" : " · On a call"}
                          </option>
                        ))}
                      {transferCloserUser.startsWith("+") && (
                        <option value={transferCloserUser}>Phone {transferCloserUser}</option>
                      )}
                      {botAgentUsers.includes(transferCloserUser) && (
                        <option value={transferCloserUser}>
                          {transferCloserUser} (AI bot — cannot be its own closer)
                        </option>
                      )}
                    </Select>
                  </Field>

                  <Field
                    label="Or transfer to a phone number"
                    description="E.164, e.g. +923009311352."
                  >
                    <Input
                      value={transferCloserUser.startsWith("+") ? transferCloserUser : ""}
                      placeholder="+923009311352"
                      onChange={(e) => {
                        const digits = e.target.value.replace(/[^\d]/g, "");
                        setTransferCloserUser(digits ? `+${digits}` : "");
                        setTransferCloserName(digits ? `Phone +${digits}` : "");
                        setSaved(false);
                      }}
                    />
                  </Field>

                  {botAgentUsers.includes(transferCloserUser) && (
                    <p className="rounded-md border border-status-warning/30 bg-status-warning-muted px-3 py-2 text-caption text-status-warning">
                      {transferCloserUser} is an AI bot — pick a human closer or phone number.
                    </p>
                  )}
                  {closersError && (
                    <p className="rounded-md border border-status-warning/30 bg-status-warning-muted px-3 py-2 text-caption text-status-warning">
                      {closersError}
                    </p>
                  )}
                  {!closersLoading && !closersError && closers.length === 0 && (
                    <p className="text-caption text-foreground-muted">
                      No closers logged in. Ask them to log into ViciDial, then Refresh.
                    </p>
                  )}
                  {transferCloserUser && (
                    <p className="rounded-md bg-brand-muted px-3 py-2 text-caption text-brand">
                      IF qualified → Warm transfer to{" "}
                      <span className="font-medium text-foreground">
                        {transferCloserName || transferCloserUser}
                      </span>
                    </p>
                  )}

                  <div className="space-y-4 border-t border-surface-border-subtle pt-5">
                    <p className="text-caption font-medium text-foreground-secondary">
                      Transfer lines
                    </p>
                    <div>
                      <p className="mb-2 text-2xs text-foreground-faint">
                        Transfer line (qualified)
                      </p>
                      <Textarea
                        value={transferLine}
                        onChange={(e) => {
                          setTransferLine(e.target.value);
                          setSaved(false);
                        }}
                      />
                    </div>
                    <div>
                      <p className="mb-2 text-2xs text-foreground-faint">Not interested line</p>
                      <Textarea
                        value={notInterestedLine}
                        onChange={(e) => {
                          setNotInterestedLine(e.target.value);
                          setSaved(false);
                        }}
                      />
                    </div>
                  </div>
                </div>
              )}

              {section === "test" && (
                <div className="space-y-4">
                  <p className="text-caption text-foreground-muted">
                    Waits until the GPU worker is ready, then activates ViciDial and dials.
                  </p>
                  <Field label="Phone number" description="Include country code (E.164).">
                    <Input
                      value={testPhone}
                      onChange={(e) => setTestPhone(e.target.value)}
                      placeholder="+923142222318"
                      className="font-mono text-sm"
                    />
                  </Field>
                  <Field
                    label="ViciDial list ID"
                    description="Active lead list tied to this campaign (e.g. 101)."
                  >
                    <Input
                      value={testListId}
                      onChange={(e) => setTestListId(e.target.value)}
                      placeholder="101"
                      className="font-mono text-sm"
                    />
                  </Field>
                  <Field
                    label="Outbound caller ID"
                    description="Set once in ViciDial Admin/SQL (Test dial does not update this)."
                  >
                    <Input
                      value={testOutboundCid}
                      onChange={(e) => setTestOutboundCid(e.target.value)}
                      placeholder="+19482194316"
                      className="font-mono text-sm"
                    />
                  </Field>
                  <Button
                    type="button"
                    className="w-full"
                    onClick={() => void runTestDial()}
                    disabled={testDialing || botCount === 0 || !vicidialCampaignId.trim()}
                  >
                    <PhoneCall className="h-4 w-4" />
                    {testDialing ? "Waiting for GPU & dialing…" : "Test dial this number"}
                  </Button>
                  {testDialing && testDialProgress.length > 0 && (
                    <p className="max-h-48 overflow-y-auto whitespace-pre-wrap rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-2xs text-amber-100/90">
                      {testDialProgress.join("\n")}
                    </p>
                  )}
                  {testDialResult && (
                    <p className="whitespace-pre-wrap rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-2xs text-emerald-100/90">
                      {testDialResult}
                    </p>
                  )}
                </div>
              )}

              {section === "overview" && (
                <div className="space-y-4">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <OverviewTile label="Campaign" value={campaignName || "—"} />
                    <OverviewTile label="Script" value={scriptLabel || "—"} />
                    <OverviewTile label="ViciDial ID" value={vicidialCampaignId || "—"} mono />
                    <OverviewTile
                      label="Status"
                      value={
                        campaignStatus === "running" ? "Running — agents can go live" : "Paused"
                      }
                    />
                    <OverviewTile label="Agents assigned" value={`${botCount}`} />
                    <OverviewTile
                      label="Assigned closer"
                      value={transferCloserName || transferCloserUser || "Not selected"}
                    />
                    <OverviewTile
                      label="Knowledge topics"
                      value={`${knowledge.filter((k) => k.answer.trim()).length}`}
                    />
                    <OverviewTile label="Qualifying questions" value={`${questions.length}`} />
                  </div>
                </div>
              )}
            </div>
          </div>
        </section>
      </div>
    </div>
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

function OverviewTile({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="rounded-md border border-surface-border-subtle bg-surface-overlay/50 px-3 py-3">
      <p className="text-2xs uppercase tracking-wide text-foreground-faint">{label}</p>
      <p
        className={cn(
          "mt-1 truncate text-body text-foreground-secondary",
          mono && "font-mono text-caption",
        )}
      >
        {value}
      </p>
    </div>
  );
}
