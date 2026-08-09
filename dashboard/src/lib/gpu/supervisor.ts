const SUPERVISOR_SECRET = process.env.GPU_SUPERVISOR_SECRET?.trim() ?? "";

export type GpuSupervisorWorker = {
  bot_id: string;
  campaign_id: string;
  vicidial_agent_user: string;
  media_port: number;
  running: boolean;
  uptime_sec: number;
  media_ready: boolean;
};

export type GpuSupervisorStatus = {
  ok: boolean;
  error?: string | null;
  worker_count: number;
  workers: GpuSupervisorWorker[];
};

function supervisorBaseUrl(): string | null {
  const baseUrl = process.env.GPU_SUPERVISOR_URL?.trim().replace(/\/$/, "");
  return baseUrl || null;
}

function supervisorHeaders(): HeadersInit {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (SUPERVISOR_SECRET) {
    headers.authorization = `Bearer ${SUPERVISOR_SECRET}`;
    headers["x-supervisor-secret"] = SUPERVISOR_SECRET;
  }
  return headers;
}

function parseSupervisorWorker(raw: Record<string, unknown>): GpuSupervisorWorker {
  const mediaHealth =
    raw.media_health && typeof raw.media_health === "object"
      ? (raw.media_health as Record<string, unknown>)
      : {};
  const mediaReady =
    mediaHealth.ready === true ||
    String(mediaHealth.ready ?? "").toLowerCase() === "true";
  return {
    bot_id: String(raw.bot_id ?? ""),
    campaign_id: String(raw.campaign_id ?? ""),
    vicidial_agent_user: String(raw.vicidial_agent_user ?? ""),
    media_port: typeof raw.media_port === "number" ? raw.media_port : 0,
    running: raw.running === true,
    uptime_sec: typeof raw.uptime_sec === "number" ? raw.uptime_sec : 0,
    media_ready: mediaReady,
  };
}

/** GET /status — worker processes + prewarm progress (requires GPU_SUPERVISOR_URL). */
export async function fetchGpuSupervisorStatus(): Promise<GpuSupervisorStatus | null> {
  const baseUrl = supervisorBaseUrl();
  if (!baseUrl) return null;

  try {
    const res = await fetch(`${baseUrl}/status`, {
      headers: supervisorHeaders(),
      cache: "no-store",
    });
    const raw = await res.text();
    if (!raw.trim()) return null;
    const body = JSON.parse(raw) as Record<string, unknown>;
    const workersRaw = Array.isArray(body.workers) ? body.workers : [];
    return {
      ok: body.ok !== false,
      error: typeof body.error === "string" ? body.error : null,
      worker_count:
        typeof body.worker_count === "number" ? body.worker_count : workersRaw.length,
      workers: workersRaw
        .filter((row): row is Record<string, unknown> => typeof row === "object" && row !== null)
        .map(parseSupervisorWorker),
    };
  } catch {
    return null;
  }
}

/** Tail /tmp/fleet_worker_*.log via supervisor (last N lines). */
export async function fetchGpuWorkerLogTail(botId: string, lines = 8): Promise<string[]> {
  const baseUrl = supervisorBaseUrl();
  if (!baseUrl || !botId.trim()) return [];

  try {
    const q = new URLSearchParams({ bot_id: botId.trim(), lines: String(lines) });
    const res = await fetch(`${baseUrl}/logs/worker?${q}`, {
      headers: supervisorHeaders(),
      cache: "no-store",
    });
    const body = (await res.json()) as { lines?: string[] };
    return Array.isArray(body.lines) ? body.lines : [];
  } catch {
    return [];
  }
}

/** Notify GPU fleet supervisor after Run/Pause campaign (optional). */
export async function syncGpuSupervisor(campaignId: string, action: "start" | "stop") {
  const baseUrl = supervisorBaseUrl();
  if (!baseUrl) {
    return {
      ok: true,
      configured: false,
      message: "GPU supervisor URL not set — workers rely on poll loop only.",
    };
  }

  const path = action === "start" ? "/sync" : "/stop";
  const query = `?campaign_id=${encodeURIComponent(campaignId)}`;

  let res: Response;
  try {
    res = await fetch(`${baseUrl}${path}${query}`, {
      method: "POST",
      headers: supervisorHeaders(),
      cache: "no-store",
    });
  } catch (err) {
    const reason = err instanceof Error ? err.message : "network error";
    throw new Error(
      `GPU supervisor unreachable at ${baseUrl} (${reason}). ` +
        "Leave GPU_SUPERVISOR_URL unset to use the poll loop (~20s), or expose port 8770 on the GPU.",
    );
  }

  const raw = await res.text();
  let body: Record<string, unknown> = {};
  if (raw.trim()) {
    try {
      body = JSON.parse(raw) as Record<string, unknown>;
    } catch {
      throw new Error(
        `GPU supervisor returned non-JSON (${res.status}): ${raw.slice(0, 200) || "(empty body)"}`,
      );
    }
  } else if (!res.ok) {
    throw new Error(`Supervisor ${path} failed (${res.status}) with empty body.`);
  }

  if (!res.ok) {
    const detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body);
    throw new Error(detail || `Supervisor ${path} failed (${res.status}).`);
  }

  const workerCount = typeof body.worker_count === "number" ? body.worker_count : 0;
  return {
    ok: true,
    configured: true,
    message:
      workerCount > 0
        ? `${workerCount} GPU worker(s) synced.`
        : "Supervisor synced — check ViciDial agent logins if no workers started.",
    body,
  };
}
