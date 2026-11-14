import type { VicidialCredentials } from "./closers";
import { normalizeVicidialUrl } from "./connection";

export type HopperFixInput = {
  vicidialCampaignId: string;
  phone_code: string;
  phone_number: string;
};

/**
 * action=preflight on ai_fronter_fix_hopper.php: dialer screens, AudioSocket bridge,
 * stuck vicidial_auto_calls rows (cleared), remote agent reset to READY.
 * `skipped` when the helper is not installed — test dial continues without it.
 */
export async function runVicidialPreflight(
  creds: VicidialCredentials,
  input: { vicidialCampaignId: string; agentUser: string },
): Promise<{ ok: boolean; skipped: boolean; detail: string }> {
  const secret = process.env.VICIDIAL_HOPPER_FIX_SECRET?.trim();
  const base = normalizeVicidialUrl(creds.baseUrl);
  if (!secret || !base) {
    return {
      ok: true,
      skipped: true,
      detail: "Dialer preflight skipped (VICIDIAL_HOPPER_FIX_SECRET not set).",
    };
  }

  const path =
    process.env.VICIDIAL_HOPPER_FIX_PATH?.trim() || "/vicidial/ai_fronter_fix_hopper.php";
  const url = new URL(path.startsWith("/") ? path : `/${path}`, `${base}/`);
  url.searchParams.set("secret", secret);
  url.searchParams.set("action", "preflight");
  url.searchParams.set("campaign_id", input.vicidialCampaignId);
  url.searchParams.set("agent_user", input.agentUser);

  try {
    const res = await fetch(url.toString(), {
      method: "GET",
      cache: "no-store",
    });
    const text = (await res.text()).trim();
    const first = text.split(/\r?\n/)[0] ?? "";
    if (first.startsWith("OK:")) {
      return { ok: true, skipped: false, detail: text.replace(/\r?\n/g, " ") };
    }
    if (first.startsWith("ERROR:") && !first.includes("phone_number required")) {
      return {
        ok: false,
        skipped: false,
        detail: text.replace(/^ERROR:\s*/, "").replace(/\r?\n/g, " "),
      };
    }
    return {
      ok: true,
      skipped: true,
      detail:
        "Dialer preflight not available — copy the latest ai_fronter_fix_hopper.php to /var/www/html/vicidial/.",
    };
  } catch (err) {
    const reason = err instanceof Error ? err.message : "fetch failed";
    return {
      ok: true,
      skipped: true,
      detail: `Dialer preflight unreachable (${reason}).`,
    };
  }
}

/** action=load_hopper / clear_hopper on ai_fronter_fix_hopper.php. */
export async function runVicidialHopperAction(
  creds: VicidialCredentials,
  input: { vicidialCampaignId: string; action: "load_hopper" | "clear_hopper" },
): Promise<{ ok: boolean; detail: string }> {
  const secret = process.env.VICIDIAL_HOPPER_FIX_SECRET?.trim();
  const base = normalizeVicidialUrl(creds.baseUrl);
  if (!secret || !base) {
    return {
      ok: false,
      detail: "VICIDIAL_HOPPER_FIX_SECRET or ViciDial URL not set — cannot load the hopper.",
    };
  }
  const path =
    process.env.VICIDIAL_HOPPER_FIX_PATH?.trim() || "/vicidial/ai_fronter_fix_hopper.php";
  const url = new URL(path.startsWith("/") ? path : `/${path}`, `${base}/`);
  url.searchParams.set("secret", secret);
  url.searchParams.set("action", input.action);
  url.searchParams.set("campaign_id", input.vicidialCampaignId);
  try {
    const res = await fetch(url.toString(), {
      method: "GET",
      cache: "no-store",
    });
    const line = (await res.text()).trim().split(/\r?\n/)[0] ?? "";
    if (line.startsWith("OK:")) return { ok: true, detail: line.replace(/^OK:\s*/, "") };
    if (line.includes("phone_number required")) {
      return {
        ok: false,
        detail:
          "Dialer helper is outdated — copy the latest ai_fronter_fix_hopper.php to /var/www/html/vicidial/.",
      };
    }
    return {
      ok: false,
      detail: line.replace(/^ERROR:\s*/, "") || `HTTP ${res.status}`,
    };
  } catch (err) {
    return {
      ok: false,
      detail: `Dialer helper unreachable (${err instanceof Error ? err.message : "fetch failed"}).`,
    };
  }
}

/** Call ai_fronter_fix_hopper.php on the dialer (see agent/scripts/vicidial/). */
export async function fixVicidialHopperReady(
  creds: VicidialCredentials,
  input: HopperFixInput,
): Promise<{ ok: boolean; detail: string }> {
  const secret = process.env.VICIDIAL_HOPPER_FIX_SECRET?.trim();
  if (!secret) {
    return {
      ok: false,
      detail:
        "VICIDIAL_HOPPER_FIX_SECRET not set — install ai_fronter_fix_hopper.php on the dialer or run fix_test_hopper.sh via SSH.",
    };
  }

  const base = normalizeVicidialUrl(creds.baseUrl);
  if (!base) {
    return { ok: false, detail: "ViciDial base URL missing." };
  }

  const path =
    process.env.VICIDIAL_HOPPER_FIX_PATH?.trim() || "/vicidial/ai_fronter_fix_hopper.php";
  const url = new URL(path.startsWith("/") ? path : `/${path}`, `${base}/`);
  url.searchParams.set("secret", secret);
  url.searchParams.set("campaign_id", input.vicidialCampaignId);
  url.searchParams.set("phone_code", input.phone_code);
  url.searchParams.set("phone_number", input.phone_number);

  try {
    const res = await fetch(url.toString(), {
      method: "GET",
      cache: "no-store",
    });
    const text = (await res.text()).trim();
    const line = text.split(/\r?\n/)[0] ?? text;
    if (!res.ok || line.startsWith("ERROR:")) {
      return { ok: false, detail: line || `HTTP ${res.status}` };
    }
    return { ok: true, detail: line };
  } catch (err) {
    const reason = err instanceof Error ? err.message : "fetch failed";
    return {
      ok: false,
      detail: `Hopper fix URL unreachable (${reason}). Install ai_fronter_fix_hopper.php under ${base}${path}`,
    };
  }
}
