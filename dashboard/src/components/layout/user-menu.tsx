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
    <div className="flex items-center gap-3 pl-2">
      {email && (
        <span className="hidden max-w-[160px] truncate text-caption text-foreground-faint md:inline">
          {email}
        </span>
      )}
      <button
        type="button"
        onClick={handleLogout}
        title="Sign out"
        className="group flex items-center gap-2 rounded-md border border-surface-border bg-surface-overlay px-2 py-1.5 transition-colors hover:border-surface-border hover:bg-surface-raised"
      >
        <span className="flex h-6 w-6 items-center justify-center rounded-sm bg-brand-muted text-2xs font-semibold text-brand">
          {initials}
        </span>
        <LogOut className="hidden h-3.5 w-3.5 text-foreground-faint group-hover:text-foreground-muted sm:block" strokeWidth={1.75} />
      </button>
    </div>
  );
}
