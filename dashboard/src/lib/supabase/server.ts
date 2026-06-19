import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { normalizeSupabaseUrl, supabaseConfigHelp } from "@/lib/supabase/config";

function resolveSupabaseUrl(url: string): string {
  const normalized = normalizeSupabaseUrl(url);
  if (!normalized.endsWith(".supabase.co")) {
    throw new Error(
      "Wrong Supabase URL in .env.local. Use https://YOUR_PROJECT.supabase.co from Settings → API.",
    );
  }
  return normalized;
}

export async function createClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!url || !key) {
    throw new Error(supabaseConfigHelp());
  }

  const cookieStore = await cookies();

  return createServerClient(resolveSupabaseUrl(url), key, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          cookiesToSet.forEach(({ name, value, options }) => {
            cookieStore.set(name, value, options);
          });
        } catch {
          // Called from a Server Component — middleware will refresh the session.
        }
      },
    },
  });
}
