import { createBrowserClient } from "@supabase/ssr";

function assertSupabaseUrl(url: string) {
  if (url.includes("supabase.com/dashboard")) {
    throw new Error(
      "Wrong Supabase URL. Use the API URL from Settings → API, e.g. https://YOUR_PROJECT.supabase.co — not the dashboard browser link.",
    );
  }
  if (!url.endsWith(".supabase.co")) {
    throw new Error(
      "Supabase URL should look like https://YOUR_PROJECT.supabase.co (from Supabase → Settings → API → Project URL).",
    );
  }
}

export function createClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!url || !key) {
    throw new Error(
      "Missing NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY. Copy .env.example to .env.local.",
    );
  }

  assertSupabaseUrl(url);

  return createBrowserClient(url, key);
}
export function isSupabaseConfigured() {
  return Boolean(
    process.env.NEXT_PUBLIC_SUPABASE_URL && process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
  );
}
