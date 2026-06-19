import type { VicidialCredentials } from "./closers";
import { fetchVicidialClosers, fetchVicidialVersion } from "./closers";

export type VicidialConnectionResult = {
  message: string;
  agentCount: number;
};

export function normalizeVicidialUrl(url: string): string {
  let trimmed = url.trim().replace(/\/$/, "");
  if (!trimmed) return "";
  if (!/^https?:\/\//i.test(trimmed)) {
    trimmed = `https://${trimmed}`;
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
