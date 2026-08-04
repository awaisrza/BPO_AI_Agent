const SUPERVISOR_SECRET = process.env.GPU_SUPERVISOR_SECRET?.trim() ?? "";

function supervisorHeaders(): HeadersInit {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (SUPERVISOR_SECRET) {
    headers.authorization = `Bearer ${SUPERVISOR_SECRET}`;
    headers["x-supervisor-secret"] = SUPERVISOR_SECRET;
  }
  return headers;
}

/** Notify GPU fleet supervisor after Run/Pause campaign (optional). */
export async function syncGpuSupervisor(campaignId: string, action: "start" | "stop") {
  const baseUrl = process.env.GPU_SUPERVISOR_URL?.trim().replace(/\/$/, "");
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

  const body = (await res.json()) as Record<string, unknown>;
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
