import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

function assertSupabaseUrl(url: string) {
  if (url.includes("supabase.com/dashboard") || !url.endsWith(".supabase.co")) {
    throw new Error(
      "Wrong Supabase URL in .env.local. Use https://YOUR_PROJECT.supabase.co from Settings → API.",
    );
  }
}

export async function createClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!url || !key) {
    throw new Error(
      "Missing NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY. Copy .env.example to .env.local.",
    );
  }

  assertSupabaseUrl(url);

  const cookieStore = await cookies();

  return createServerClient(url, key, {
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
