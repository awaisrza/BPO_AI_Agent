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

  // API user often lacks modify_remote_agents — activate via dialer MySQL helper.
  const remote = await runVicidialHopperAction(creds, {
    vicidialCampaignId: input.vicidialCampaignId,
    action: "set_remote_agent",
    agentUser: input.agentUser,
    status: "ACTIVE",
  });
  steps.push({ step: "activate_remote_agent", ok: remote.ok, detail: remote.detail });
  if (!remote.ok) {
    return {
      ok: false,
      steps,
      message: `Could not activate remote agent ${input.agentUser}: ${remote.detail}`,
    };
  }

  // ASTVDremote logs the agent in a few seconds after status becomes ACTIVE.
  let preflight = await runVicidialPreflight(creds, input);
  for (let i = 0; i < 10 && !preflight.ok && /not logged in/i.test(preflight.detail); i++) {
    await new Promise((resolve) => setTimeout(resolve, 3_000));
    preflight = await runVicidialPreflight(creds, input);
  }
  steps.push({ step: "dialer_preflight", ok: preflight.ok, detail: preflight.detail });
  if (!preflight.ok) {
    return {
      ok: false,
      steps,
      message: `Dialer not ready — no calls placed: ${preflight.detail}`,
    };
  }

  // Drop any stale READY/NEW hopper rows left from a previous run, then reload.
  // "1 already queued" often means a stuck lead that ASTVDauto never dials.
  const cleared = await runVicidialHopperAction(creds, {
    vicidialCampaignId: input.vicidialCampaignId,
    action: "clear_hopper",
  });
  steps.push({ step: "clear_stale_hopper", ok: cleared.ok, detail: cleared.detail });

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
  const remote = await runVicidialHopperAction(creds, {
    vicidialCampaignId: input.vicidialCampaignId,
    action: "set_remote_agent",
    agentUser: input.agentUser,
    status: "INACTIVE",
  });
  steps.push({ step: "remote_agent_inactive", ok: remote.ok, detail: remote.detail });
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
