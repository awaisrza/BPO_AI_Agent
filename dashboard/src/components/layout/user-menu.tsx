"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { LogOut } from "lucide-react";
import { createClient, isSupabaseConfigured } from "@/lib/supabase/client";

export function UserMenu() {
  const router = useRouter();
  const [initials, setInitials] = useState("?");
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    if (!isSupabaseConfigured()) return;

    const supabase = createClient();

    async function load() {
      const {
        data: { user },
      } = await supabase.auth.getUser();

      if (!user) return;

      setEmail(user.email ?? null);

      const { data: profile } = await supabase
        .from("profiles")
        .select("name")
        .eq("id", user.id)
        .single();

      const label = profile?.name ?? user.email ?? "?";
      setInitials(
        label
          .split(" ")
          .map((part: string) => part[0])
          .join("")
          .slice(0, 2)
          .toUpperCase(),
      );
    }

    load();
  }, []);

  async function handleLogout() {
    if (!isSupabaseConfigured()) return;
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/login");
    router.refresh();
  }

  return (
    <div className="flex items-center gap-1.5">
      <div className="flex items-center gap-2 rounded-md border border-surface-border-subtle bg-surface-overlay/55 py-1 pl-1 pr-2.5">
        <span className="flex h-7 w-7 items-center justify-center rounded-[8px] bg-gradient-to-br from-brand/35 to-brand/10 text-2xs font-semibold text-brand ring-1 ring-brand/20">
          {initials}
        </span>
        {email && (
          <span className="hidden max-w-[10rem] truncate text-caption text-foreground-muted sm:inline">
            {email}
          </span>
        )}
      </div>
      <button
        type="button"
        onClick={handleLogout}
        title="Sign out"
        aria-label="Sign out"
        className="rounded-md border border-transparent p-2 text-foreground-faint transition-colors hover:border-surface-border-subtle hover:bg-surface-overlay hover:text-foreground-secondary"
      >
        <LogOut className="h-3.5 w-3.5" strokeWidth={1.75} />
      </button>
    </div>
  );
}
