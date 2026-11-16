export type GpuOrchestratorConfig = {
  supervisorUrl: string;
  supervisorSecret: string;
  runpodApiKey: string;
  runpodPodId: string;
  vastApiKey: string;
  vastInstanceId: string;
  stopPodOnIdle: boolean;
  healthTimeoutMs: number;
};

export function getGpuOrchestratorConfig(): GpuOrchestratorConfig | null {
  const supervisorUrl = process.env.GPU_SUPERVISOR_URL?.trim().replace(/\/$/, "") ?? "";
  const vastApiKey = process.env.VAST_API_KEY?.trim() ?? "";
  const vastInstanceId = process.env.VAST_INSTANCE_ID?.trim() ?? "";
  const runpodApiKey = process.env.RUNPOD_API_KEY?.trim() ?? "";
  const runpodPodId = process.env.RUNPOD_POD_ID?.trim() ?? "";

  const hasSupervisor = Boolean(supervisorUrl);
  const hasVast = Boolean(vastApiKey && vastInstanceId);
  const hasRunpod = Boolean(runpodApiKey && runpodPodId);
  if (!hasSupervisor && !hasVast && !hasRunpod) return null;

  return {
    supervisorUrl,
    supervisorSecret: process.env.GPU_SUPERVISOR_SECRET?.trim() ?? "",
    runpodApiKey,
    runpodPodId,
    vastApiKey,
    vastInstanceId,
    stopPodOnIdle: process.env.GPU_STOP_POD_ON_IDLE === "true",
    healthTimeoutMs: Number(process.env.GPU_HEALTH_TIMEOUT_MS ?? "300000"),
  };
}

export function isGpuOrchestratorConfigured() {
  return getGpuOrchestratorConfig() !== null;
}

export function isVastAutoStartConfigured() {
  return Boolean(
    process.env.VAST_API_KEY?.trim() && process.env.VAST_INSTANCE_ID?.trim(),
  );
}
