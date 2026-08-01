import type { VicidialCredentials } from "./closers";
import { fetchVicidialApi } from "./closers";

export type VicidialCampaignOption = {
  id: string;
  name: string;
};

/** Parse ViciDial non_agent_api campaigns_list (pipe default, or csv when stage=csv). */
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

  const delimiter = first.includes("|") ? "|" : ",";
  const headerParts = first.split(delimiter).map((part) => part.trim().toLowerCase());
  const hasHeader = headerParts[0] === "campaign_id";
  const dataLines = hasHeader ? lines.slice(1) : lines;

  const campaigns: VicidialCampaignOption[] = [];

  for (const line of dataLines) {
    if (line.startsWith("ERROR:")) continue;

    const parts = line.split(delimiter);
    const id = parts[0]?.trim();
    const name = parts[1]?.trim() || id;
    if (!id || id.toLowerCase() === "campaign_id") continue;

    campaigns.push({ id, name: name || id });
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
