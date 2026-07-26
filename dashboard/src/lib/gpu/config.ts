export type GpuOrchestratorConfig = {
  supervisorUrl: string;
  supervisorSecret: string;
  runpodApiKey: string;
  runpodPodId: string;
  stopPodOnIdle: boolean;
  healthTimeoutMs: number;
};

export function getGpuOrchestratorConfig(): GpuOrchestratorConfig | null {
  const supervisorUrl = process.env.GPU_SUPERVISOR_URL?.trim().replace(/\/$/, "") ?? "";
  if (!supervisorUrl) return null;

  return {
    supervisorUrl,
    supervisorSecret: process.env.GPU_SUPERVISOR_SECRET?.trim() ?? "",
    runpodApiKey: process.env.RUNPOD_API_KEY?.trim() ?? "",
    runpodPodId: process.env.RUNPOD_POD_ID?.trim() ?? "",
    stopPodOnIdle: process.env.GPU_STOP_POD_ON_IDLE === "true",
    healthTimeoutMs: Number(process.env.GPU_HEALTH_TIMEOUT_MS ?? "300000"),
  };
}

export function isGpuOrchestratorConfigured() {
  return Boolean(process.env.GPU_SUPERVISOR_URL?.trim());
}
