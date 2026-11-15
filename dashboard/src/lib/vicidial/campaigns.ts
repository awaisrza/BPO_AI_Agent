import type { VicidialCredentials } from "./closers";
import { fetchVicidialApi, parseCsvLine } from "./closers";

export type VicidialCampaignOption = {
  id: string;
  name: string;
};

/** First token only — users often paste a full CSV row from ViciDial exports. */
export function normalizeVicidialCampaignId(raw: string): string {
  const t = raw.trim();
  if (!t) return "";
  if (t.includes(",")) return (t.split(",")[0] ?? t).trim();
  if (t.includes("|")) return (t.split("|")[0] ?? t).trim();
  return t;
}

function parseCampaignRow(line: string, delimiter: "|" | ","): VicidialCampaignOption | null {
  const cols =
    delimiter === "|" ? line.split("|").map((c) => c.trim()) : parseCsvLine(line);
  const id = normalizeVicidialCampaignId(cols[0] ?? "");
  if (!id || id.toLowerCase() === "campaign_id") return null;
  const name = (cols[1] ?? id).trim() || id;
  return { id, name };
}

/** Parse ViciDial non_agent_api campaigns_list (pipe default, or csv). */
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

  const delimiter: "|" | "," = lines.some((l) => l.includes("|")) ? "|" : ",";
  let dataLines = lines;

  const headerCols =
    delimiter === "|"
      ? lines[0].split("|").map((c) => c.trim().toLowerCase())
      : parseCsvLine(lines[0]).map((c) => c.toLowerCase());
  if (headerCols[0] === "campaign_id") {
    dataLines = lines.slice(1);
  }

  const byId = new Map<string, VicidialCampaignOption>();
  for (const line of dataLines) {
    if (line.startsWith("ERROR:")) continue;
    const row = parseCampaignRow(line, delimiter);
    if (row) byId.set(row.id, row);
  }

  return [...byId.values()].sort((a, b) => a.id.localeCompare(b.id));
}

export async function fetchVicidialCampaigns(
  creds: VicidialCredentials,
): Promise<VicidialCampaignOption[]> {
  // Pipe format avoids commas inside dial_statuses breaking CSV parsing.
  const text = await fetchVicidialApi(creds, {
    function: "campaigns_list",
    stage: "pipe",
    header: "YES",
  });
  return parseCampaignsList(text);
}
