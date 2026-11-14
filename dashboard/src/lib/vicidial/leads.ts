import type { VicidialCredentials } from "./closers";
import { parseCsvLine } from "./closers";
import { normalizeVicidialUrl } from "./connection";

export type VicidialLead = {
  leadId: number;
  listId: number;
  phoneCode: string;
  phoneNumber: string;
  phone: string;
  status: string;
  firstName: string;
  lastName: string;
  name: string;
  calledCount: number;
  calledSinceLastReset: string;
  lastAttempt: string;
};

export type VicidialLeadSummary = {
  total: number;
  new: number;
  dialed: number;
  transferred: number;
  notInterested: number;
  dnc: number;
};

function helperUrl(
  creds: VicidialCredentials,
  params: Record<string, string>,
): URL | null {
  const secret = process.env.VICIDIAL_HOPPER_FIX_SECRET?.trim();
  const base = normalizeVicidialUrl(creds.baseUrl);
  if (!secret || !base) return null;
  const path =
    process.env.VICIDIAL_HOPPER_FIX_PATH?.trim() || "/vicidial/ai_fronter_fix_hopper.php";
  const url = new URL(path.startsWith("/") ? path : `/${path}`, `${base}/`);
  url.searchParams.set("secret", secret);
  for (const [k, v] of Object.entries(params)) {
    if (v) url.searchParams.set(k, v);
  }
  return url;
}

export function summarizeLeads(leads: VicidialLead[]): VicidialLeadSummary {
  const summary: VicidialLeadSummary = {
    total: leads.length,
    new: 0,
    dialed: 0,
    transferred: 0,
    notInterested: 0,
    dnc: 0,
  };
  for (const lead of leads) {
    const s = lead.status.toUpperCase();
    if (s === "NEW" || s === "CALLBK") summary.new += 1;
    else if (s === "DNC") summary.dnc += 1;
    else if (s === "XFER") summary.transferred += 1;
    else if (s === "NI") summary.notInterested += 1;
    if (lead.calledCount > 0 || lead.calledSinceLastReset === "Y") summary.dialed += 1;
  }
  return summary;
}

export function parseLeadsCsv(text: string): VicidialLead[] {
  const lines = text
    .trim()
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
  if (!lines.length || lines[0].startsWith("ERROR:")) {
    throw new Error(lines[0]?.replace(/^ERROR:\s*/i, "") || "Could not load leads.");
  }
  // Skip OK: line, then require header
  let start = 0;
  if (lines[0].startsWith("OK:")) start = 1;
  if (start >= lines.length) return [];
  const header = parseCsvLine(lines[start]).map((h) => h.toLowerCase());
  const idx = (name: string) => header.indexOf(name);
  const data = lines.slice(start + (header.includes("lead_id") ? 1 : 0));

  const leads: VicidialLead[] = [];
  for (const line of data) {
    if (line.startsWith("OK:") || line.startsWith("ERROR:")) continue;
    const cols = parseCsvLine(line);
    const leadId = Number(cols[idx("lead_id")] ?? cols[0] ?? 0);
    if (!leadId) continue;
    const phoneCode = cols[idx("phone_code")] ?? "";
    const phoneNumber = cols[idx("phone_number")] ?? "";
    const firstName = cols[idx("first_name")] ?? "";
    const lastName = cols[idx("last_name")] ?? "";
    leads.push({
      leadId,
      listId: Number(cols[idx("list_id")] ?? 0),
      phoneCode,
      phoneNumber,
      phone: phoneCode && phoneNumber ? `+${phoneCode}${phoneNumber}` : phoneNumber,
      status: (cols[idx("status")] ?? "").toUpperCase(),
      firstName,
      lastName,
      name: [firstName, lastName].filter(Boolean).join(" ") || "—",
      calledCount: Number(cols[idx("called_count")] ?? 0),
      calledSinceLastReset: cols[idx("called_since_last_reset")] ?? "",
      lastAttempt: cols[idx("last_local_call_time")] ?? "—",
    });
  }
  return leads;
}

export async function fetchVicidialLeads(
  creds: VicidialCredentials,
  input: { vicidialCampaignId: string },
): Promise<{ leads: VicidialLead[]; detail: string }> {
  const url = helperUrl(creds, {
    action: "list_leads",
    campaign_id: input.vicidialCampaignId,
  });
  if (!url) {
    throw new Error(
      "VICIDIAL_HOPPER_FIX_SECRET not set — install ai_fronter_fix_hopper.php on the dialer.",
    );
  }
  const res = await fetch(url.toString(), { method: "GET", cache: "no-store" });
  const text = (await res.text()).trim();
  const first = text.split(/\r?\n/)[0] ?? "";
  if (!first.startsWith("OK:")) {
    throw new Error(first.replace(/^ERROR:\s*/, "") || `HTTP ${res.status}`);
  }
  return { leads: parseLeadsCsv(text), detail: first.replace(/^OK:\s*/, "") };
}

export async function upsertVicidialLead(
  creds: VicidialCredentials,
  input: {
    vicidialCampaignId: string;
    phone_code: string;
    phone_number: string;
    list_id?: string;
    status?: string;
    first_name?: string;
    last_name?: string;
  },
): Promise<{ ok: boolean; detail: string }> {
  const url = helperUrl(creds, {
    action: "upsert_lead",
    campaign_id: input.vicidialCampaignId,
    phone_code: input.phone_code,
    phone_number: input.phone_number,
    list_id: input.list_id ?? "",
    status: input.status ?? "NEW",
    first_name: input.first_name ?? "Test",
    last_name: input.last_name ?? "Lead",
  });
  if (!url) {
    return {
      ok: false,
      detail: "VICIDIAL_HOPPER_FIX_SECRET not set — cannot write leads on the dialer.",
    };
  }
  try {
    const res = await fetch(url.toString(), { method: "GET", cache: "no-store" });
    const line = (await res.text()).trim().split(/\r?\n/)[0] ?? "";
    if (line.startsWith("OK:")) return { ok: true, detail: line.replace(/^OK:\s*/, "") };
    return { ok: false, detail: line.replace(/^ERROR:\s*/, "") || `HTTP ${res.status}` };
  } catch (err) {
    return {
      ok: false,
      detail: err instanceof Error ? err.message : "Dialer helper unreachable.",
    };
  }
}
