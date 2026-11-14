import type { VicidialCredentials } from "./closers";
import { fetchVicidialApi } from "./closers";
import { runVicidialHopperAction, runVicidialPreflight } from "./hopper-fix";

export type DialingStep = { step: string; ok: boolean; detail: string };

export type DialingResult = {
  ok: boolean;
  steps: DialingStep[];
  message: string;
};

async function vd(creds: VicidialCredentials, params: Record<string, string>): Promise<string> {
  try {
    return (await fetchVicidialApi(creds, params)).trim().split(/\r?\n/)[0]?.trim() ?? "";
  } catch (err) {
    return `ERROR: ${err instanceof Error ? err.message : "network error"}`;
  }
}

function apiOk(line: string): boolean {
  return Boolean(line) && !line.startsWith("ERROR:");
}

/** Activate the ViciDial campaign + bot remote agent and queue the campaign's leads. */
export async function startVicidialDialing(
  creds: VicidialCredentials,
  input: { vicidialCampaignId: string; agentUser: string },
): Promise<DialingResult> {
  const steps: DialingStep[] = [];

  const preflight = await runVicidialPreflight(creds, input);
  steps.push({
    step: "dialer_preflight",
    ok: preflight.ok,
    detail: preflight.detail,
  });
  if (!preflight.ok) {
    return {
      ok: false,
      steps,
      message: `Dialer not ready — no calls placed: ${preflight.detail}`,
    };
  }

  const campaignLine = await vd(creds, {
    function: "update_campaign",
    campaign_id: input.vicidialCampaignId,
    active: "Y",
    dial_method: "RATIO",
    auto_dial_level: "1.1",
    hopper_level: "100",
  });
  steps.push({
    step: "update_campaign",
    ok: apiOk(campaignLine),
    detail: campaignLine,
  });
  if (!apiOk(campaignLine)) {
    return {
      ok: false,
      steps,
      message: `Could not activate ViciDial campaign: ${campaignLine}`,
    };
  }

  const remoteLine = await vd(creds, {
    function: "update_remote_agent",
    agent_user: input.agentUser,
    status: "ACTIVE",
    campaign_id: input.vicidialCampaignId,
    number_of_lines: "1",
  });
  const remoteOk = apiOk(remoteLine) || remoteLine.includes("ALREADY ACTIVE");
  steps.push({ step: "update_remote_agent", ok: remoteOk, detail: remoteLine });

  const hopper = await runVicidialHopperAction(creds, {
    vicidialCampaignId: input.vicidialCampaignId,
    action: "load_hopper",
  });
  steps.push({ step: "load_hopper", ok: hopper.ok, detail: hopper.detail });
  if (!hopper.ok) {
    return { ok: false, steps, message: `No calls queued: ${hopper.detail}` };
  }

  return {
    ok: true,
    steps,
    message: `Dialing started — ${hopper.detail}. Expect the first call within ~30–60s.`,
  };
}

/** Stop new dials: remote agent INACTIVE and queued (not yet dialed) leads removed. */
export async function stopVicidialDialing(
  creds: VicidialCredentials,
  input: { vicidialCampaignId: string; agentUser: string },
): Promise<DialingResult> {
  const steps: DialingStep[] = [];
  const remoteLine = await vd(creds, {
    function: "update_remote_agent",
    agent_user: input.agentUser,
    status: "INACTIVE",
  });
  steps.push({
    step: "remote_agent_inactive",
    ok: apiOk(remoteLine),
    detail: remoteLine,
  });
  const hopper = await runVicidialHopperAction(creds, {
    vicidialCampaignId: input.vicidialCampaignId,
    action: "clear_hopper",
  });
  steps.push({ step: "clear_hopper", ok: hopper.ok, detail: hopper.detail });
  return {
    ok: steps.every((s) => s.ok),
    steps,
    message: steps.every((s) => s.ok)
      ? "Dialing stopped — no new calls will be placed."
      : `Dialing stop incomplete: ${steps
          .filter((s) => !s.ok)
          .map((s) => `${s.step}: ${s.detail}`)
          .join("; ")}`,
  };
}
