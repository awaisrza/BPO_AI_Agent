type RunPodGraphqlResponse<T> = {
  data?: T;
  errors?: { message: string }[];
};

type PodResumeData = {
  podResume: { id: string; desiredStatus: string };
};

type PodStopData = {
  podStop: { id: string; desiredStatus: string };
};

type PodQueryData = {
  pod: { id: string; desiredStatus: string; runtime?: { uptimeInSeconds?: number } | null } | null;
};

const RUNPOD_GRAPHQL = "https://api.runpod.io/graphql";

async function runpodGraphql<T>(apiKey: string, query: string): Promise<T> {
  const res = await fetch(`${RUNPOD_GRAPHQL}?api_key=${encodeURIComponent(apiKey)}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ query }),
    cache: "no-store",
  });

  const json = (await res.json()) as RunPodGraphqlResponse<T>;
  if (json.errors?.length) {
    throw new Error(json.errors.map((e) => e.message).join("; "));
  }
  if (!json.data) {
    throw new Error("RunPod API returned no data.");
  }
  return json.data;
}

export async function resumeRunPodPod(apiKey: string, podId: string) {
  const data = await runpodGraphql<PodResumeData>(
    apiKey,
    `mutation { podResume(input: { podId: "${podId}", gpuCount: 1 }) { id desiredStatus } }`,
  );
  return data.podResume;
}

export async function stopRunPodPod(apiKey: string, podId: string) {
  const data = await runpodGraphql<PodStopData>(
    apiKey,
    `mutation { podStop(input: { podId: "${podId}" }) { id desiredStatus } }`,
  );
  return data.podStop;
}

export async function getRunPodPodStatus(apiKey: string, podId: string) {
  const data = await runpodGraphql<PodQueryData>(
    apiKey,
    `query { pod(input: { podId: "${podId}" }) { id desiredStatus runtime { uptimeInSeconds } } }`,
  );
  return data.pod;
}

export async function waitForRunPodRunning(
  apiKey: string,
  podId: string,
  timeoutMs = 180_000,
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const pod = await getRunPodPodStatus(apiKey, podId);
    const status = pod?.desiredStatus?.toUpperCase() ?? "";
    if (status === "RUNNING") return;
    await new Promise((r) => setTimeout(r, 5000));
  }
  throw new Error(`RunPod pod ${podId} did not reach RUNNING within ${timeoutMs / 1000}s.`);
}
