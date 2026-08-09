import { fetchGpuWorkerHealth } from "./worker-health";
import { fetchGpuSupervisorStatus, fetchGpuWorkerLogTail, syncGpuSupervisor } from "./supervisor";

export type GpuWarmupPhase =
  | "not_configured"
  | "supervisor_unconfigured"
  | "offline"
  | "waiting_supervisor"
  | "prewarming"
  | "busy"
  | "ready"
  | "error";

export type GpuWarmupStatus = {
  phase: GpuWarmupPhase;
  ready: boolean;
  message: string;
  supervisorConfigured: boolean;
  healthConfigured: boolean;
  workerReachable: boolean;
  logTail: string[];
  waitedMs?: number;
};

function prewarmTimeoutMs(): number {
  return parseInt(process.env.GPU_WORKER_PREWARM_TIMEOUT_MS ?? "900000", 10);
}

function pollMs(): number {
  return parseInt(process.env.GPU_WORKER_READY_POLL_MS ?? "3000", 10);
}

function phaseMessage(input: {
  phase: GpuWarmupPhase;
  supervisorConfigured: boolean;
  workerRunning: boolean;
  uptimeSec: number;
  logTail: string[];
}): string {
  switch (input.phase) {
    case "not_configured":
      return "Set GPU_WORKER_HEALTH_URL in dashboard .env (Vast public port → internal 10200).";
    case "supervisor_unconfigured":
      return (
        "GPU worker health URL is set but worker is offline. " +
        "SSH to the GPU and run: cd /workspace/BPO_AI_Agent/agent && nohup python run_supervisor.py > /tmp/supervisor.log 2>&1 & " +
        "Optional: expose port 8770 on Vast and set GPU_SUPERVISOR_URL for instant sync + live logs."
      );
    case "offline":
      return (
        "GPU worker not reachable. Start the supervisor on the GPU (see above). " +
        "Campaign is set to running — the supervisor poll loop starts workers within ~20s when it is up."
      );
    case "waiting_supervisor":
      return (
        "Waiting for GPU supervisor to spawn a worker (~20s poll). " +
        "If this persists, SSH to the GPU and check: pgrep -af run_supervisor; tail /tmp/supervisor.log"
      );
    case "prewarming":
      return input.workerRunning
        ? `Worker is prewarming models (${input.uptimeSec}s elapsed — usually 5–15 min on cold start).`
        : "Worker process starting — prewarm not begun yet.";
    case "busy":
      return "Worker is up but finishing the previous call (ready:false). Wait or hang up the prior call.";
    case "ready":
      return "GPU worker ready for a call.";
    case "error":
      return "GPU warmup failed — check supervisor and worker logs on the GPU.";
    default:
      return "Checking GPU…";
  }
}

/** Current warmup snapshot (supervisor status + worker /health + optional log tail). */
export async function fetchGpuWarmupStatus(options?: {
  campaignId?: string;
  botId?: string;
}): Promise<GpuWarmupStatus> {
  const health = await fetchGpuWorkerHealth();
  const supervisorConfigured = Boolean(process.env.GPU_SUPERVISOR_URL?.trim());
  const healthConfigured = health.configured;

  if (!healthConfigured) {
    return {
      phase: "not_configured",
      ready: false,
      message: health.message,
      supervisorConfigured,
      healthConfigured: false,
      workerReachable: false,
      logTail: [],
    };
  }

  if (health.ready) {
    return {
      phase: "ready",
      ready: true,
      message: health.message,
      supervisorConfigured,
      healthConfigured,
      workerReachable: true,
      logTail: [],
    };
  }

  if (health.reachable && !health.ready) {
    return {
      phase: "busy",
      ready: false,
      message: health.message,
      supervisorConfigured,
      healthConfigured,
      workerReachable: true,
      logTail: [],
    };
  }

  let logTail: string[] = [];
  let workerRunning = false;
  let uptimeSec = 0;

  if (supervisorConfigured) {
    const sup = await fetchGpuSupervisorStatus();
    if (sup?.ok !== false && sup?.workers?.length) {
      const worker =
        (options?.botId
          ? sup.workers.find((w) => w.bot_id === options.botId)
          : undefined) ?? sup.workers[0];
      if (worker) {
        workerRunning = worker.running;
        uptimeSec = worker.uptime_sec;
        if (worker.media_ready) {
          return {
            phase: "ready",
            ready: true,
            message: "GPU worker media server is ready.",
            supervisorConfigured,
            healthConfigured,
            workerReachable: true,
            logTail: [],
          };
        }
        logTail = await fetchGpuWorkerLogTail(worker.bot_id, 8);
        return {
          phase: "prewarming",
          ready: false,
          message: phaseMessage({
            phase: "prewarming",
            supervisorConfigured,
            workerRunning,
            uptimeSec,
            logTail,
          }),
          supervisorConfigured,
          healthConfigured,
          workerReachable: false,
          logTail,
        };
      }
    }
    if (sup && sup.worker_count === 0) {
      return {
        phase: "waiting_supervisor",
        ready: false,
        message: phaseMessage({
          phase: "waiting_supervisor",
          supervisorConfigured,
          workerRunning: false,
          uptimeSec: 0,
          logTail: [],
        }),
        supervisorConfigured,
        healthConfigured,
        workerReachable: false,
        logTail: [],
      };
    }
  }

  return {
    phase: supervisorConfigured ? "waiting_supervisor" : "supervisor_unconfigured",
    ready: false,
    message: phaseMessage({
      phase: supervisorConfigured ? "waiting_supervisor" : "supervisor_unconfigured",
      supervisorConfigured,
      workerRunning,
      uptimeSec,
      logTail,
    }),
    supervisorConfigured,
    healthConfigured,
    workerReachable: false,
    logTail,
  };
}

/** Mark campaign running and nudge GPU supervisor (when URL is configured). */
export async function startGpuWarmup(campaignId: string): Promise<{ message: string }> {
  try {
    const gpu = await syncGpuSupervisor(campaignId, "start");
    return {
      message: gpu.configured
        ? gpu.message
        : `${gpu.message} Worker should start on the next supervisor poll (~20s) if run_supervisor.py is running on the GPU.`,
    };
  } catch (err) {
    const reason = err instanceof Error ? err.message : "supervisor sync failed";
    return {
      message: `${reason} If the supervisor poll loop is running on the GPU, the worker should still start.`,
    };
  }
}

/** Poll until ready or prewarm timeout. Returns timeline of status messages. */
export async function waitForGpuWarmup(options: {
  campaignId?: string;
  botId?: string;
  timeoutMs?: number;
  onProgress?: (status: GpuWarmupStatus) => void;
}): Promise<GpuWarmupStatus & { events: string[]; waitedMs: number }> {
  const timeoutMs = options.timeoutMs ?? prewarmTimeoutMs();
  const started = Date.now();
  const events: string[] = [];
  let last: GpuWarmupStatus | null = null;

  while (Date.now() - started < timeoutMs) {
    const status = await fetchGpuWarmupStatus({
      campaignId: options.campaignId,
      botId: options.botId,
    });
    last = status;
    options.onProgress?.(status);

    const line = `[${Math.round((Date.now() - started) / 1000)}s] ${status.message}`;
    if (events[events.length - 1] !== line) {
      events.push(line);
      if (status.logTail.length) {
        for (const logLine of status.logTail.slice(-3)) {
          events.push(`  log: ${logLine}`);
        }
      }
    }

    if (status.ready) {
      return { ...status, events, waitedMs: Date.now() - started };
    }

    await new Promise((resolve) => setTimeout(resolve, pollMs()));
  }

  const fallback =
    last ??
    ({
      phase: "error",
      ready: false,
      message: "GPU warmup status unknown.",
      supervisorConfigured: false,
      healthConfigured: false,
      workerReachable: false,
      logTail: [],
    } satisfies GpuWarmupStatus);

  return {
    ...fallback,
    ready: false,
    phase: "error",
    message:
      `${fallback.message} Timed out after ${Math.round((Date.now() - started) / 1000)}s. ` +
      "On the GPU: pgrep -af run_supervisor; tail /tmp/fleet_worker_*.log; curl -s http://127.0.0.1:10200/health",
    events,
    waitedMs: Date.now() - started,
  };
}
