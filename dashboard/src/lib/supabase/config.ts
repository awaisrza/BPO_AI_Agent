/** API base URL. Accepts dashboard browser links and normalizes them. */
export function normalizeSupabaseUrl(url: string): string {
  const trimmed = url.trim();
  const dashboardMatch = trimmed.match(
    /supabase\.com\/dashboard\/project\/([a-z0-9]+)/i,
  );
  if (dashboardMatch) {
    return `https://${dashboardMatch[1]}.supabase.co`;
  }
  return trimmed;
}

export function isSupabaseConfigured() {
  return Boolean(
    process.env.NEXT_PUBLIC_SUPABASE_URL && process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
  );
}

export function supabaseConfigHelp(): string {
  const onVercel =
    process.env.VERCEL === "1" ||
    (typeof window !== "undefined" &&
      (window.location.hostname.endsWith(".vercel.app") ||
        window.location.hostname.includes("vercel.app")));

  if (onVercel) {
    return (
      "Supabase keys are missing on Vercel. " +
      "Go to Vercel → your project → Settings → Environment Variables. " +
      "Add NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY (check Production), " +
      "then Deployments → Redeploy."
    );
  }

  return (
    "Supabase keys missing locally. " +
    "Create dashboard/.env.local with NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY, " +
    "then restart: npm run dev"
  );
}
