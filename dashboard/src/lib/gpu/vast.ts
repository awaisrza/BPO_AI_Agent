/** Vast.ai REST helpers — start/stop instances for fleet supervisor auto-boot. */

const VAST_API_BASE = "https://console.vast.ai/api/v0";

export type VastInstanceStatus = {
  id: string;
  actualStatus: string;
  intendedStatus: string;
  publicIp: string | null;
};

type VastInstanceRaw = {
  id?: number | string;
  actual_status?: string | null;
  intended_status?: string | null;
  public_ipaddr?: string | null;
  public_ip?: string | null;
  ssh_host?: string | null;
};

function authHeaders(apiKey: string): HeadersInit {
  return {
    Authorization: `Bearer ${apiKey}`,
    Accept: "application/json",
    "Content-Type": "application/json",
  };
}

function normalizeInstance(raw: VastInstanceRaw, fallbackId: string): VastInstanceStatus {
  const id = raw.id != null ? String(raw.id) : fallbackId;
  const publicIp =
    (typeof raw.public_ipaddr === "string" && raw.public_ipaddr) ||
    (typeof raw.public_ip === "string" && raw.public_ip) ||
    null;
  return {
    id,
    actualStatus: (raw.actual_status ?? "").toLowerCase(),
    intendedStatus: (raw.intended_status ?? "").toLowerCase(),
    publicIp,
  };
}

function parseInstancePayload(body: unknown, instanceId: string): VastInstanceStatus {
  if (!body || typeof body !== "object") {
    throw new Error(`Vast instance ${instanceId}: empty response`);
  }
  const root = body as Record<string, unknown>;
  if (root.instances && typeof root.instances === "object" && !Array.isArray(root.instances)) {
    return normalizeInstance(root.instances as VastInstanceRaw, instanceId);
  }
  if (Array.isArray(root.instances) && root.instances[0]) {
    return normalizeInstance(root.instances[0] as VastInstanceRaw, instanceId);
  }
  return normalizeInstance(root as VastInstanceRaw, instanceId);
}

export async function getVastInstance(
  apiKey: string,
  instanceId: string,
): Promise<VastInstanceStatus> {
  const res = await fetch(`${VAST_API_BASE}/instances/${encodeURIComponent(instanceId)}/`, {
    headers: authHeaders(apiKey),
    cache: "no-store",
  });
  const text = await res.text();
  let body: unknown = {};
  if (text.trim()) {
    try {
      body = JSON.parse(text);
    } catch {
      throw new Error(`Vast instance ${instanceId}: non-JSON (${res.status}) ${text.slice(0, 120)}`);
    }
  }
  if (!res.ok) {
    const detail =
      typeof body === "object" &&
      body &&
      "msg" in body &&
      typeof (body as { msg?: unknown }).msg === "string"
        ? (body as { msg: string }).msg
        : `HTTP ${res.status}`;
    throw new Error(`Vast get instance failed: ${detail}`);
  }
  return parseInstancePayload(body, instanceId);
}

/** Start a stopped/exited instance. No-op if already running. */
export async function startVastInstance(
  apiKey: string,
  instanceId: string,
): Promise<VastInstanceStatus> {
  const current = await getVastInstance(apiKey, instanceId);
  if (current.actualStatus === "running") {
    return current;
  }

  const res = await fetch(`${VAST_API_BASE}/instances/${encodeURIComponent(instanceId)}/`, {
    method: "PUT",
    headers: authHeaders(apiKey),
    body: JSON.stringify({ state: "running" }),
    cache: "no-store",
  });
  const text = await res.text();
  let body: unknown = {};
  if (text.trim()) {
    try {
      body = JSON.parse(text);
    } catch {
      /* ignore */
    }
  }
  if (!res.ok) {
    const detail =
      typeof body === "object" &&
      body &&
      "msg" in body &&
      typeof (body as { msg?: unknown }).msg === "string"
        ? (body as { msg: string }).msg
        : `HTTP ${res.status}`;
    throw new Error(`Vast start instance failed: ${detail}`);
  }

  return getVastInstance(apiKey, instanceId);
}

/**
 * Run a short command on the instance (Vast execute API). Max 512 chars.
 * Used to restart the fleet supervisor after a GPU reboot without SSH.
 */
export async function executeVastCommand(
  apiKey: string,
  instanceId: string,
  command: string,
): Promise<{ ok: boolean; resultUrl?: string; message: string }> {
  const trimmed = command.trim().slice(0, 512);
  if (!trimmed) {
    return { ok: false, message: "Empty Vast execute command." };
  }
  const res = await fetch(
    `${VAST_API_BASE}/instances/command/${encodeURIComponent(instanceId)}/`,
    {
      method: "PUT",
      headers: authHeaders(apiKey),
      body: JSON.stringify({ command: trimmed }),
      cache: "no-store",
    },
  );
  const text = await res.text();
  let body: Record<string, unknown> = {};
  if (text.trim()) {
    try {
      body = JSON.parse(text) as Record<string, unknown>;
    } catch {
      /* ignore */
    }
  }
  if (!res.ok) {
    const detail =
      typeof body.msg === "string"
        ? body.msg
        : typeof body.error === "string"
          ? body.error
          : `HTTP ${res.status}`;
    return { ok: false, message: `Vast execute failed: ${detail}` };
  }
  return {
    ok: true,
    resultUrl: typeof body.result_url === "string" ? body.result_url : undefined,
    message:
      typeof body.msg === "string"
        ? body.msg
        : "Restart command sent to GPU — waiting for worker health.",
  };
}

/** Default onstart-equivalent: restart fleet supervisor + worker on the GPU. */
export function vastSupervisorRestartCommand(): string {
  return (
    process.env.GPU_VAST_RESTART_CMD?.trim() ||
    "cd /workspace/BPO_AI_Agent/agent && . .venv/bin/activate 2>/dev/null; bash scripts/restart_fleet_supervisor.sh"
  );
}

export async function stopVastInstance(
  apiKey: string,
  instanceId: string,
): Promise<VastInstanceStatus> {
  const res = await fetch(`${VAST_API_BASE}/instances/${encodeURIComponent(instanceId)}/`, {
    method: "PUT",
    headers: authHeaders(apiKey),
    body: JSON.stringify({ state: "stopped" }),
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Vast stop instance failed (${res.status}): ${text.slice(0, 160)}`);
  }
  return getVastInstance(apiKey, instanceId);
}

const FATAL_STATUSES = new Set(["exited", "unknown", "offline"]);

export async function waitForVastRunning(
  apiKey: string,
  instanceId: string,
  timeoutMs = 300_000,
): Promise<VastInstanceStatus> {
  const deadline = Date.now() + timeoutMs;
  let last: VastInstanceStatus | null = null;
  while (Date.now() < deadline) {
    last = await getVastInstance(apiKey, instanceId);
    if (last.actualStatus === "running") return last;
    if (FATAL_STATUSES.has(last.actualStatus)) {
      throw new Error(
        `Vast instance ${instanceId} is ${last.actualStatus} — will not reach running. ` +
          "Start it from the Vast console or recreate the instance.",
      );
    }
    await new Promise((r) => setTimeout(r, 5000));
  }
  throw new Error(
    `Vast instance ${instanceId} did not reach running within ${Math.round(timeoutMs / 1000)}s ` +
      `(last status: ${last?.actualStatus || "unknown"}).`,
  );
}
