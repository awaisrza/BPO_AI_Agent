import type { SupabaseClient } from "@supabase/supabase-js";
import type { VicidialCredentials } from "./closers";
import { fetchVicidialClosers, fetchVicidialVersion } from "./closers";

export type VicidialConnectionResult = {
  message: string;
  agentCount: number;
};

function defaultSchemeForHost(host: string): "http" | "https" {
  // ViciDial installs almost always serve plain HTTP; bare IPs must not default to HTTPS.
  if (/^\d{1,3}(\.\d{1,3}){3}(:\d+)?$/.test(host)) return "http";
  if (/^localhost(:\d+)?$/i.test(host) || host.startsWith("127.")) return "http";
  return "https";
}

export function normalizeVicidialUrl(url: string): string {
  let trimmed = url.trim().replace(/\/$/, "");
  if (!trimmed) return "";
  if (!/^https?:\/\//i.test(trimmed)) {
    trimmed = `${defaultSchemeForHost(trimmed)}://${trimmed}`;
  }

  // Users often paste the admin login page — keep only the server root.
  trimmed = trimmed.replace(/\/vicidial\/admin\.php.*$/i, "");
  trimmed = trimmed.replace(/\/agc\/vicidial\.php.*$/i, "");
  trimmed = trimmed.replace(/\/+$/, "");

  return trimmed;
}

export async function testVicidialConnection(
  creds: VicidialCredentials,
): Promise<VicidialConnectionResult> {
  if (!creds.baseUrl || !creds.user || !creds.pass) {
    throw new Error("Server URL, API user, and API password are required.");
  }

  try {
    const version = await fetchVicidialVersion(creds);
    try {
      const closers = await fetchVicidialClosers(creds);
      return {
        message:
          closers.length > 0
            ? `Connected (${version}). ${closers.length} closer${closers.length === 1 ? "" : "s"} logged in.`
            : `Connected (${version}). No closers logged in right now — ask your team to log into ViciDial.`,
        agentCount: closers.length,
      };
    } catch (err) {
      const message = err instanceof Error ? err.message : "Connection failed.";
      if (message.includes("PERMISSION TO GET AGENT INFO")) {
        return {
          message:
            `API reachable (${version}), but user "${creds.user}" cannot list agents. ` +
            "In ViciDial Admin → Users → set User Level 7+, enable View Reports, and API Access.",
          agentCount: 0,
        };
      }
      if (message.includes("NO LOGGED IN AGENTS")) {
        return {
          message: `Connected (${version}). No closers logged in right now.`,
          agentCount: 0,
        };
      }
      throw err;
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : "Connection failed.";
    if (message.includes("NO LOGGED IN AGENTS")) {
      return {
        message: "Connected. No closers logged in right now.",
        agentCount: 0,
      };
    }
    throw err;
  }
}

type OrgVicidialFields = {
  vicidial_url: string | null;
  vicidial_user: string | null;
  vicidial_pass: string | null;
};

/** Same org join as campaign readiness — works without service role key. */
export async function getVicidialCredsForCampaign(
  supabase: SupabaseClient,
  campaignId: string,
): Promise<VicidialCredentials & { configured: boolean }> {
  const { data: campaign } = await supabase
    .from("campaigns")
    .select("organizations(vicidial_url, vicidial_user, vicidial_pass)")
    .eq("id", campaignId)
    .maybeSingle();

  const org = campaign?.organizations as OrgVicidialFields | OrgVicidialFields[] | null;
  const orgRow = Array.isArray(org) ? (org[0] ?? null) : org;
  return resolveVicidialCreds(
    orgRow ?? { vicidial_url: null, vicidial_user: null, vicidial_pass: null },
  );
}

export function resolveVicidialCreds(
  org: {
    vicidial_url: string | null;
    vicidial_user: string | null;
    vicidial_pass: string | null;
  },
  overrides?: {
    vicidial_url?: string;
    vicidial_user?: string;
    vicidial_pass?: string;
  },
): VicidialCredentials & { configured: boolean } {
  const baseUrl = normalizeVicidialUrl(
    overrides?.vicidial_url?.trim() || org.vicidial_url || process.env.VICIDIAL_BASE_URL || "",
  );
  const user = (overrides?.vicidial_user?.trim() || org.vicidial_user || process.env.VICIDIAL_API_USER || "").trim();
  const pass = overrides?.vicidial_pass?.trim() || org.vicidial_pass || process.env.VICIDIAL_API_PASS || "";
  const userGroups = process.env.VICIDIAL_CLOSER_USER_GROUPS || undefined;

  return {
    baseUrl,
    user,
    pass,
    userGroups,
    configured: Boolean(baseUrl && user && pass),
  };
}
