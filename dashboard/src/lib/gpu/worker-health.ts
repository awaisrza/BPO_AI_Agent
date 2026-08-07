export type GpuWorkerHealthStatus = {
  configured: boolean;
  reachable: boolean;
  ready: boolean;
  message: string;
  body: Record<string, unknown>;
};

function parseBool(value: unknown): boolean {
  if (value === true || value === 1) return true;
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    return normalized === "true" || normalized === "1" || normalized === "yes";
  }
  return false;
}

function isHealthUp(body: Record<string, unknown>): boolean {
  if (parseBool(body.ready)) return true;
  if (parseBool(body.ok)) return true;
  const status = body.status;
  if (typeof status === "string") {
    const normalized = status.toLowerCase();
    if (normalized === "ok" || normalized === "healthy") return true;
  }
  return false;
}

function isCallSlotReady(body: Record<string, unknown>): boolean {
  if ("ready" in body) return parseBool(body.ready);
  // Older workers without ready — treat reachable + ok as ready.
  return isHealthUp(body);
}

function healthUrl(): string | null {
  const url = process.env.GPU_WORKER_HEALTH_URL?.trim();
  return url || null;
}

function formatExtras(body: Record<string, unknown>): string {
  const agent = typeof body.agent_user === "string" ? body.agent_user : "";
  const campaign =
    typeof body.vicidial_campaign_id === "string" ? body.vicidial_campaign_id : "";
  return [agent && `agent ${agent}`, campaign && `campaign ${campaign}`]
    .filter(Boolean)
    .join(", ");
}

/** Single GET to the fleet worker /health endpoint. */
export async function fetchGpuWorkerHealth(): Promise<GpuWorkerHealthStatus> {
  const url = healthUrl();
  if (!url) {
    return {
      configured: false,
      reachable: false,
      ready: false,
      message:
        "GPU_WORKER_HEALTH_URL not set — test dial cannot wait for a free call slot. Set it to http://GPU_IP:PUBLIC_PORT/health (Vast maps 10200).",
      body: {},
    };
  }

  try {
    const res = await fetch(url, { cache: "no-store" });
    const raw = await res.text();
    let body: Record<string, unknown> = {};
    if (raw.trim()) {
      try {
        body = JSON.parse(raw) as Record<string, unknown>;
      } catch {
        return {
          configured: true,
          reachable: true,
          ready: false,
          message: `GPU worker health returned non-JSON (${res.status}): ${raw.slice(0, 120)}`,
          body: {},
        };
      }
    }

    const reachable = res.ok || raw.trim().length > 0;
    const ready = reachable && isCallSlotReady(body);
    const extras = formatExtras(body);

    if (!reachable) {
      return {
        configured: true,
        reachable: false,
        ready: false,
        message: `GPU worker not responding (${res.status}) at ${url}.`,
        body,
      };
    }

    if (ready) {
      return {
        configured: true,
        reachable: true,
        ready: true,
        message: extras
          ? `GPU worker ready for a call (${extras}).`
          : "GPU worker ready for a call.",
        body,
      };
    }

    const busyHint =
      "ready" in body
        ? "Worker is up but busy finishing the previous call."
        : "Worker responded but is not ready.";

    return {
      configured: true,
      reachable: true,
      ready: false,
      message: `${busyHint}${extras ? ` (${extras})` : ""}`,
      body,
    };
  } catch (err) {
    const reason = err instanceof Error ? err.message : "network error";
    return {
      configured: true,
      reachable: false,
      ready: false,
      message: `GPU worker not reachable at ${url} (${reason}). Start fleet_worker on the GPU and open the Vast port for 10200.`,
      body: {},
    };
  }
}

/** Poll until ready:true or timeout — use before adding a test lead to the hopper. */
export async function waitForGpuWorkerReady(options?: {
  timeoutMs?: number;
  pollMs?: number;
}): Promise<GpuWorkerHealthStatus & { waitedMs: number }> {
  const timeoutMs = options?.timeoutMs ?? parseInt(process.env.GPU_WORKER_READY_TIMEOUT_MS ?? "45000", 10);
  const pollMs = options?.pollMs ?? parseInt(process.env.GPU_WORKER_READY_POLL_MS ?? "2000", 10);

  const started = Date.now();
  let last = await fetchGpuWorkerHealth();

  if (!last.configured) {
    return { ...last, waitedMs: 0 };
  }

  while (!last.ready && Date.now() - started < timeoutMs) {
    await new Promise((resolve) => setTimeout(resolve, pollMs));
    last = await fetchGpuWorkerHealth();
  }

  const waitedMs = Date.now() - started;

  if (last.ready) {
    return {
      ...last,
      message:
        waitedMs > 500
          ? `${last.message} (waited ${Math.round(waitedMs / 1000)}s for call slot.)`
          : last.message,
      waitedMs,
    };
  }

  return {
    ...last,
    message:
      `${last.message} Timed out after ${Math.round(waitedMs / 1000)}s waiting for ready:true — ` +
      "the prior call may still be cleaning up. Wait 30s and try again, or restart fleet_worker on the GPU.",
    waitedMs,
  };
}

/** Legacy helper — true when worker responds and call slot is free. */
export async function checkGpuWorkerHealth(): Promise<{
  configured: boolean;
  ok: boolean;
  ready: boolean;
  message: string;
}> {
  const status = await fetchGpuWorkerHealth();
  return {
    configured: status.configured,
    ok: status.reachable && status.ready,
    ready: status.ready,
    message: status.message,
  };
}
