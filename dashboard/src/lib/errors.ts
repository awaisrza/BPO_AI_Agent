type SupabaseLikeError = {
  message?: string;
  code?: string;
  details?: string;
  hint?: string;
};

export function formatSupabaseError(err: unknown, fallback: string): string {
  if (!err) return fallback;
  if (err instanceof Error) return err.message;

  const e = err as SupabaseLikeError;
  if (e.message) {
    if (e.code === "PGRST116") {
      return "Your account is missing a profile. Refresh the page and try again.";
    }
    if (e.message.includes("row-level security")) {
      return "Permission denied. Run supabase/schema.sql in Supabase SQL Editor, then sign out and back in.";
    }
    if (e.message.includes("does not exist")) {
      return `${e.message} — Open Supabase → SQL Editor → run the full file: dashboard/supabase/setup.sql`;
    }
    return e.message;
  }

  return fallback;
}
