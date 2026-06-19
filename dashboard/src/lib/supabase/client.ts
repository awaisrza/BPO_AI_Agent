import { createBrowserClient } from "@supabase/ssr";
import { isSupabaseConfigured, normalizeSupabaseUrl, supabaseConfigHelp } from "@/lib/supabase/config";

export { isSupabaseConfigured, supabaseConfigHelp };

function assertSupabaseUrl(url: string) {
  const normalized = normalizeSupabaseUrl(url);
  if (!normalized.endsWith(".supabase.co")) {
    throw new Error(
      "Supabase URL should look like https://YOUR_PROJECT.supabase.co (from Supabase → Settings → API → Project URL).",
    );
  }
  return normalized;
}

export function createClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!url || !key) {
    throw new Error(supabaseConfigHelp());
  }

  return createBrowserClient(assertSupabaseUrl(url), key);
}
