import { createAdminClient } from "@/lib/supabase/admin";
import { getGpuOrchestratorConfig } from "@/lib/gpu/config";
import { resumeRunPodPod, stopRunPodPod, waitForRunPodRunning } from "@/lib/gpu/runpod";
import {
  startVastInstance,
  stopVastInstance,
  waitForVastRunning,
} from "@/lib/gpu/vast";
import { fetchGpuWorkerHealth } from "@/lib/gpu/worker-health";

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
): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  const url = `${baseUrl}/health`;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url, {
        headers: supervisorHeaders(secret),
        cache: "no-store",
      });
      if (res.ok) return true;
    } catch {
      // Pod may still be booting / port not mapped
    }
    await new Promise((r) => setTimeout(r, 3000));
  }
  return false;
}

async function waitForWorkerHealth(timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const health = await fetchGpuWorkerHealth();
    if (health.ready) return;
    if (!health.configured) {
      throw new Error(health.message);
    }
    await new Promise((r) => setTimeout(r, 3000));
  }
  throw new Error(
    `GPU worker health did not become ready within ${Math.round(timeoutMs / 1000)}s. ` +
      "Check Vast onstart (restart_fleet_supervisor.sh) and GPU_WORKER_HEALTH_URL (public → 10200).",
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

/**
 * If the fleet worker is offline and Vast (or RunPod) is configured, start the host,
 * wait for health, then POST /sync when supervisor URL is reachable.
 */
export async function startGpuForCampaign(campaignId: string): Promise<OrchestrateResult> {
  const config = getGpuOrchestratorConfig();
  if (!config) {
    return {
      ok: true,
      configured: false,
      message:
        "GPU auto-start is not configured. Add VAST_API_KEY + VAST_INSTANCE_ID " +
        "(and optionally GPU_SUPERVISOR_URL) to dashboard/.env.local.",
    };
  }

  let podInfo: { id: string; desiredStatus: string } | undefined;
  const health = await fetchGpuWorkerHealth();
  const needsHostStart = !health.ready;

  if (needsHostStart && config.vastApiKey && config.vastInstanceId) {
    const started = await startVastInstance(config.vastApiKey, config.vastInstanceId);
    podInfo = { id: started.id, desiredStatus: started.intendedStatus || "running" };
    await waitForVastRunning(config.vastApiKey, config.vastInstanceId, config.healthTimeoutMs);
  } else if (needsHostStart && config.runpodApiKey && config.runpodPodId) {
    podInfo = await resumeRunPodPod(config.runpodApiKey, config.runpodPodId);
    await waitForRunPodRunning(config.runpodApiKey, config.runpodPodId, config.healthTimeoutMs);
  }

  const hostHint = podInfo
    ? ` Host ${podInfo.id} started.`
    : needsHostStart
      ? " Host was already expected online."
      : "";

  // Prefer supervisor when mapped; otherwise wait on worker /health only.
  let supervisor: Record<string, unknown> | undefined;
  if (config.supervisorUrl) {
    const supervisorOk = await waitForSupervisorHealth(
      config.supervisorUrl,
      config.supervisorSecret,
      Math.min(config.healthTimeoutMs, 90_000),
    );
    if (supervisorOk) {
      try {
        await waitForWorkerHealth(Math.min(config.healthTimeoutMs, 180_000));
      } catch {
        // Sync can still spawn workers; warmup poll waits for ready:true.
      }
      supervisor = await callSupervisor(
        config.supervisorUrl,
        config.supervisorSecret,
        "/sync",
        campaignId,
      );
      const workerCount =
        typeof supervisor.worker_count === "number" ? supervisor.worker_count : 0;
      return {
        ok: true,
        configured: true,
        message:
          workerCount > 0
            ? `GPU fleet started — ${workerCount} agent worker(s) running.${hostHint}`
            : `GPU supervisor online; waiting for workers.${hostHint}`,
        pod: podInfo,
        supervisor,
      };
    }
  }

  // Supervisor URL missing or not reachable (common when Vast maps 53604→53604).
  await waitForWorkerHealth(config.healthTimeoutMs);
  return {
    ok: true,
    configured: true,
    message:
      `GPU worker is ready via health URL.${hostHint} ` +
      (config.supervisorUrl
        ? "Supervisor URL is set but unreachable — remap Vast public port → internal 8770, or comment out GPU_SUPERVISOR_URL."
        : "Relying on instance onstart + poll loop (GPU_SUPERVISOR_URL unset)."),
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

  let supervisor: Record<string, unknown> | undefined;
  if (config.supervisorUrl) {
    try {
      supervisor = await callSupervisor(
        config.supervisorUrl,
        config.supervisorSecret,
        "/stop",
        campaignId,
      );
    } catch {
      // Host may already be down
    }
  }

  let podInfo: { id: string; desiredStatus: string } | undefined;
  const shouldStopHost =
    config.stopPodOnIdle && !(await anyRunningCampaigns(campaignId));

  if (shouldStopHost && config.vastApiKey && config.vastInstanceId) {
    const stopped = await stopVastInstance(config.vastApiKey, config.vastInstanceId);
    podInfo = { id: stopped.id, desiredStatus: stopped.intendedStatus || "stopped" };
  } else if (shouldStopHost && config.runpodApiKey && config.runpodPodId) {
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
