import type { VicidialCredentials } from "./closers";
import { fetchVicidialApi } from "./closers";

export type VicidialCampaignOption = {
  id: string;
  name: string;
};

/** Parse ViciDial non_agent_api campaigns_list response (one campaign id per line). */
export function parseCampaignsList(text: string): VicidialCampaignOption[] {
  const lines = text
    .trim()
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  if (lines.length === 0) return [];

  const first = lines[0];
  if (first.startsWith("ERROR:")) {
    throw new Error(first.replace(/^ERROR:\s*/i, ""));
  }

  const campaigns: VicidialCampaignOption[] = [];

  for (const line of lines) {
    if (line.startsWith("ERROR:")) continue;
    // Skip header lines some installs return
    if (/^campaign/i.test(line) && line.includes("|")) continue;

    const id = line.split("|")[0]?.trim() || line.trim();
    if (!id || id.toLowerCase() === "campaign_id") continue;

    campaigns.push({ id, name: id });
  }

  return campaigns.sort((a, b) => a.id.localeCompare(b.id));
}

export async function fetchVicidialCampaigns(
  creds: VicidialCredentials,
): Promise<VicidialCampaignOption[]> {
  const text = await fetchVicidialApi(creds, {
    function: "campaigns_list",
    stage: "csv",
    header: "YES",
  });
  return parseCampaignsList(text);
}
