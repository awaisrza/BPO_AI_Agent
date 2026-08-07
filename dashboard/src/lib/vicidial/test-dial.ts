import type { VicidialCredentials } from "./closers";
import { fetchVicidialApi } from "./closers";

export type TestDialInput = {
  vicidialCampaignId: string;
  remoteAgentUser: string;
  phone_code: string;
  phone_number: string;
  list_id: string;
  outbound_cid?: string;
};

export type TestDialStep = {
  step: string;
  ok: boolean;
  detail: string;
};

export type TestDialResult = {
  ok: boolean;
  steps: TestDialStep[];
  hopperPreview: string;
  message: string;
};

function firstLine(text: string): string {
  return text.trim().split(/\r?\n/)[0]?.trim() ?? "";
}

function vicidialStepOk(text: string): boolean {
  const line = firstLine(text);
  if (!line) return false;
  if (line.startsWith("ERROR:")) return false;
  return true;
}

function vicidialError(text: string, fallback: string): string {
  const line = firstLine(text);
  if (line.startsWith("ERROR:")) {
    return line.replace(/^ERROR:\s*/i, "");
  }
  return fallback;
}

async function vd(
  creds: VicidialCredentials,
  params: Record<string, string>,
): Promise<string> {
  try {
    return await fetchVicidialApi(creds, params);
  } catch (err) {
    const reason = err instanceof Error ? err.message : "network error";
    return `ERROR: ${reason}`;
  }
}

/** Mirror agent/scripts/vicidial/run_test_dial.sh for dashboard one-click test. */
export async function runVicidialTestDial(
  creds: VicidialCredentials,
  input: TestDialInput,
): Promise<TestDialResult> {
  const steps: TestDialStep[] = [];

  const versionText = await vd(creds, { function: "version" });
  steps.push({
    step: "api_version",
    ok: vicidialStepOk(versionText),
    detail: firstLine(versionText),
  });

  const campaignParams: Record<string, string> = {
    function: "update_campaign",
    campaign_id: input.vicidialCampaignId,
    active: "Y",
    dial_method: "RATIO",
    auto_dial_level: "1.1",
    hopper_level: "100",
  };
  // Do not send outbound_cid — ViciDial API stores digits-only (no +), which breaks Telnyx D35.
  // Set campaign_cid='+19482194316' once in ViciDial Admin or MySQL.

  const campaignText = await vd(creds, campaignParams);
  const campaignOk = vicidialStepOk(campaignText);
  steps.push({
    step: "update_campaign",
    ok: campaignOk,
    detail: firstLine(campaignText),
  });

  const remoteText = await vd(creds, {
    function: "update_remote_agent",
    agent_user: input.remoteAgentUser,
    status: "ACTIVE",
    campaign_id: input.vicidialCampaignId,
    number_of_lines: "1",
  });
  const remoteOk = vicidialStepOk(remoteText);
  steps.push({
    step: "update_remote_agent",
    ok: remoteOk,
    detail: firstLine(remoteText),
  });

  const addLeadText = await vd(creds, {
    function: "add_lead",
    phone_number: input.phone_number,
    phone_code: input.phone_code,
    list_id: input.list_id,
    first_name: "Test",
    last_name: "Dial",
    add_to_hopper: "Y",
    hopper_local_call_time_check: "N",
    dnc_check: "N",
    campaign_dnc_check: "N",
    campaign_id: input.vicidialCampaignId,
  });
  const leadOk = vicidialStepOk(addLeadText);
  steps.push({
    step: "add_lead",
    ok: leadOk,
    detail: firstLine(addLeadText),
  });

  let hopperPreview = "";
  let hopperHasNew = false;
  try {
    hopperPreview = await vd(creds, {
      function: "hopper_list",
      campaign_id: input.vicidialCampaignId,
      stage: "csv",
      header: "YES",
    });
    const hopperLines = hopperPreview.trim().split(/\r?\n/).slice(0, 5);
    hopperPreview = hopperLines.join("\n");
    const header = hopperPreview.trim().split(/\r?\n/)[0]?.split(",") ?? [];
    const statusIdx = header.indexOf("status");
    if (statusIdx >= 0) {
      hopperHasNew = hopperPreview
        .trim()
        .split(/\r?\n/)
        .slice(1)
        .some((line) => line.split(",")[statusIdx]?.trim().toUpperCase() === "NEW");
    }
    if (hopperPreview.includes("NO LEADS IN THE HOPPER") && leadOk) {
      hopperPreview +=
        "\n(Lead was added — hopper may be empty because the auto-dialer already picked it up.)";
    }
    if (hopperHasNew) {
      hopperPreview +=
        "\n(Warning: hopper status NEW — on the ViciDial server run: UPDATE vicidial_hopper SET status='READY' WHERE campaign_id='...';)";
    }
  } catch (err) {
    hopperPreview = err instanceof Error ? err.message : "Could not read hopper.";
  }

  const criticalOk = campaignOk && leadOk;
  const e164 = `+${input.phone_code}${input.phone_number}`;
  const remoteDetail = firstLine(remoteText);

  let message: string;
  if (criticalOk) {
    if (remoteOk) {
      message = `Test lead ${e164} is in the hopper. ViciDial should dial within ~30–60s if the GPU worker is running. If the phone rings but is silent, the answered call is not bridged to the GPU bot yet — run capture_after_call.sh on the ViciDial server.`;
    } else if (remoteDetail.includes("ALREADY ACTIVE")) {
      message = `Test lead ${e164} is in the hopper. Remote agent was already active — ViciDial should dial shortly. If you hear silence on answer, run capture_after_call.sh on the ViciDial server.`;
    } else {
      message =
        `Test lead ${e164} is in the hopper. Remote agent API step skipped (${remoteDetail || "permission denied"}). ` +
        "If agent 6666 is already ACTIVE in ViciDial Admin → Remote Agents, dialing should still work.";
    }
  } else {
    const failed = steps.filter((s) => !s.ok).map((s) => s.step);
    message = `Test dial setup failed at: ${failed.join(", ")}. ${vicidialError(
      addLeadText,
      vicidialError(campaignText, "Check ViciDial API user level 8+ with modify campaigns and modify leads."),
    )}`;
  }

  return {
    ok: criticalOk,
    steps,
    hopperPreview,
    message,
  };
}
