function isHealthOk(body: Record<string, unknown>): boolean {
  const ok = body.ok;
  if (ok === true || ok === "true" || ok === "1") return true;
  const status = body.status;
  if (status === "ok" || status === "healthy") return true;
  return false;
}

/** Optional POST-test-dial check that the fleet worker HTTP health endpoint responds. */
export async function checkGpuWorkerHealth(): Promise<{
  configured: boolean;
  ok: boolean;
  message: string;
}> {
  const url = process.env.GPU_WORKER_HEALTH_URL?.trim();
  if (!url) {
    return {
      configured: false,
      ok: false,
      message:
        "GPU worker health URL not set — ensure the supervisor is running on the GPU and will pick up this campaign within ~20s.",
    };
  }

  try {
    const res = await fetch(url, { cache: "no-store" });
    const body = (await res.json()) as Record<string, unknown>;
    const healthy = res.ok && isHealthOk(body);
    const agent = typeof body.agent_user === "string" ? body.agent_user : "";
    const campaign =
      typeof body.vicidial_campaign_id === "string" ? body.vicidial_campaign_id : "";
    const extras = [agent && `agent ${agent}`, campaign && `campaign ${campaign}`]
      .filter(Boolean)
      .join(", ");

    return {
      configured: true,
      ok: healthy,
      message: healthy
        ? `GPU worker is up and healthy${extras ? ` (${extras})` : ""}.`
        : `GPU worker responded but health check failed (${res.status}). Body: ${JSON.stringify(body)}`,
    };
  } catch (err) {
    const reason = err instanceof Error ? err.message : "network error";
    return {
      configured: true,
      ok: false,
      message: `GPU worker not reachable at ${url} (${reason}). SSH to the GPU and run: curl http://127.0.0.1:8770/status`,
    };
  }
}
