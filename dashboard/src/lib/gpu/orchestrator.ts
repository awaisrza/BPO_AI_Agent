import { createAdminClient } from "@/lib/supabase/admin";
import { getGpuOrchestratorConfig } from "@/lib/gpu/config";
import { resumeRunPodPod, stopRunPodPod, waitForRunPodRunning } from "@/lib/gpu/runpod";

export type OrchestrateResult = {
  ok: boolean;
  configured: boolean;
  message: string;
  pod?: { id: string; desiredStatus: string };
  supervisor?: Record<string, unknown>;
};

function supervisorHeaders(secret: string): HeadersInit {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (secret) {
    headers.authorization = `Bearer ${secret}`;
    headers["x-supervisor-secret"] = secret;
  }
  return headers;
}

async function waitForSupervisorHealth(
  baseUrl: string,
  secret: string,
  timeoutMs: number,
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  const url = `${baseUrl}/health`;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url, {
        headers: supervisorHeaders(secret),
        cache: "no-store",
      });
      if (res.ok) return;
    } catch {
      // Pod may still be booting
    }
    await new Promise((r) => setTimeout(r, 3000));
  }
  throw new Error(
    `GPU supervisor at ${baseUrl} did not respond within ${Math.round(timeoutMs / 1000)}s. ` +
      "Ensure run_supervisor.py starts when the pod boots.",
  );
}

async function callSupervisor(
  baseUrl: string,
  secret: string,
  path: "/sync" | "/stop",
  campaignId?: string,
): Promise<Record<string, unknown>> {
  const query = campaignId ? `?campaign_id=${encodeURIComponent(campaignId)}` : "";
  const res = await fetch(`${baseUrl}${path}${query}`, {
    method: "POST",
    headers: supervisorHeaders(secret),
    cache: "no-store",
  });
  const body = (await res.json()) as Record<string, unknown>;
  if (!res.ok) {
    const detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body);
    throw new Error(detail || `Supervisor ${path} failed (${res.status}).`);
  }
  return body;
}

async function anyRunningCampaigns(excludeCampaignId?: string): Promise<boolean> {
  const admin = createAdminClient();
  if (!admin) return false;

  let query = admin.from("campaigns").select("id").eq("status", "running");
  if (excludeCampaignId) {
    query = query.neq("id", excludeCampaignId);
  }
  const { data } = await query.limit(1);
  return (data?.length ?? 0) > 0;
}

export async function startGpuForCampaign(campaignId: string): Promise<OrchestrateResult> {
  const config = getGpuOrchestratorConfig();
  if (!config) {
    return {
      ok: true,
      configured: false,
      message:
        "GPU auto-start is not configured. Add GPU_SUPERVISOR_URL to dashboard/.env.local and run python run_supervisor.py on the pod.",
    };
  }

  let podInfo: { id: string; desiredStatus: string } | undefined;

  if (config.runpodApiKey && config.runpodPodId) {
    podInfo = await resumeRunPodPod(config.runpodApiKey, config.runpodPodId);
    await waitForRunPodRunning(config.runpodApiKey, config.runpodPodId, config.healthTimeoutMs);
  }

  await waitForSupervisorHealth(
    config.supervisorUrl,
    config.supervisorSecret,
    config.healthTimeoutMs,
  );

  const supervisor = await callSupervisor(
    config.supervisorUrl,
    config.supervisorSecret,
    "/sync",
    campaignId,
  );

  const workerCount = typeof supervisor.worker_count === "number" ? supervisor.worker_count : 0;

  return {
    ok: true,
    configured: true,
    message:
      workerCount > 0
        ? `GPU fleet started — ${workerCount} agent worker(s) running.`
        : "GPU is online. Assign agents to this campaign if none are running yet.",
    pod: podInfo,
    supervisor,
  };
}

export async function stopGpuForCampaign(campaignId: string): Promise<OrchestrateResult> {
  const config = getGpuOrchestratorConfig();
  if (!config) {
    return {
      ok: true,
      configured: false,
      message: "GPU orchestrator not configured — campaign paused in dashboard only.",
    };
  }

  const supervisor = await callSupervisor(
    config.supervisorUrl,
    config.supervisorSecret,
    "/stop",
    campaignId,
  );

  let podInfo: { id: string; desiredStatus: string } | undefined;
  if (
    config.stopPodOnIdle &&
    config.runpodApiKey &&
    config.runpodPodId &&
    !(await anyRunningCampaigns(campaignId))
  ) {
    podInfo = await stopRunPodPod(config.runpodApiKey, config.runpodPodId);
  }

  return {
    ok: true,
    configured: true,
    message: "GPU agents stopped for this campaign.",
    pod: podInfo,
    supervisor,
  };
}
