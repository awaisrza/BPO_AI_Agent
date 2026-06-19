export type VicidialCloser = {
  user: string;
  fullName: string;
  status: string;
  userGroup: string;
  available: boolean;
};

export type VicidialCredentials = {
  baseUrl: string;
  user: string;
  pass: string;
  /** Pipe-delimited ViciDial user groups, e.g. "CLOSERS|SALES" */
  userGroups?: string;
};

function parseCsvLine(line: string): string[] {
  const values: string[] = [];
  let current = "";
  let inQuotes = false;

  for (let i = 0; i < line.length; i += 1) {
    const char = line[i];
    if (char === '"') {
      inQuotes = !inQuotes;
      continue;
    }
    if (char === "," && !inQuotes) {
      values.push(current.trim());
      current = "";
      continue;
    }
    current += char;
  }

  values.push(current.trim());
  return values;
}

function closerAvailability(status: string, subStatus: string): boolean {
  const normalized = status.toUpperCase();
  const sub = subStatus.toUpperCase();
  if (normalized === "INCALL") return false;
  if (["RING", "DIAL", "3-WAY", "PREVIEW"].includes(sub)) return false;
  return normalized === "PAUSED" || normalized === "READY";
}

export function parseLoggedInAgentsCsv(text: string): VicidialCloser[] {
  const lines = text
    .trim()
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  if (lines.length === 0) return [];

  if (lines[0].startsWith("ERROR:")) {
    throw new Error(lines[0].replace(/^ERROR:\s*/i, ""));
  }

  const header = parseCsvLine(lines[0]).map((h) => h.toLowerCase());
  const dataLines = header.includes("user") ? lines.slice(1) : lines;

  const idx = {
    user: header.indexOf("user"),
    status: header.indexOf("status"),
    fullName: header.indexOf("full_name"),
    userGroup: header.indexOf("user_group"),
    subStatus: header.indexOf("sub_status"),
  };

  const closers: VicidialCloser[] = [];

  for (const line of dataLines) {
    const cols = parseCsvLine(line);
    const user = idx.user >= 0 ? cols[idx.user] : cols[0];
    if (!user) continue;

    const status = idx.status >= 0 ? cols[idx.status] ?? "" : "";
    const subStatus = idx.subStatus >= 0 ? cols[idx.subStatus] ?? "" : "";
    const fullName = idx.fullName >= 0 ? cols[idx.fullName] ?? user : user;
    const userGroup = idx.userGroup >= 0 ? cols[idx.userGroup] ?? "" : "";

    closers.push({
      user,
      fullName,
      status,
      userGroup,
      available: closerAvailability(status, subStatus),
    });
  }

  return closers.sort((a, b) => {
    if (a.available !== b.available) return a.available ? -1 : 1;
    return a.fullName.localeCompare(b.fullName);
  });
}

export async function fetchVicidialApi(
  creds: VicidialCredentials,
  params: Record<string, string>,
): Promise<string> {
  const query = new URLSearchParams({
    source: "ai-fronter",
    user: creds.user,
    pass: creds.pass,
    ...params,
  });
  const url = `${creds.baseUrl.replace(/\/$/, "")}/vicidial/non_agent_api.php?${query}`;
  const res = await fetch(url, { cache: "no-store" });
  const text = await res.text();
  if (!res.ok) {
    throw new Error(`ViciDial returned ${res.status}`);
  }
  return text;
}

export async function fetchVicidialVersion(creds: VicidialCredentials): Promise<string> {
  const text = await fetchVicidialApi(creds, { function: "version" });
  const line = text.trim().split(/\r?\n/)[0] ?? "";
  if (line.startsWith("ERROR:")) {
    throw new Error(line.replace(/^ERROR:\s*/i, ""));
  }
  return line;
}

export async function fetchVicidialClosers(
  creds: VicidialCredentials,
): Promise<VicidialCloser[]> {
  const params: Record<string, string> = {
    function: "logged_in_agents",
    stage: "csv",
    header: "YES",
    show_sub_status: "YES",
  };

  if (creds.userGroups) {
    params.user_groups = creds.userGroups;
  }

  const text = await fetchVicidialApi(creds, params);
  return parseLoggedInAgentsCsv(text);
}
