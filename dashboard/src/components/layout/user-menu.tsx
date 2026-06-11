"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
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
    <div className="relative flex items-center gap-2">
      {email && (
        <span className="hidden text-xs text-zinc-600 sm:inline">{email}</span>
      )}
      <button
        type="button"
        onClick={handleLogout}
        title="Sign out"
        className="flex h-8 w-8 items-center justify-center rounded-full bg-white/[0.06] text-xs font-medium text-zinc-400 transition-colors hover:bg-white/[0.1] hover:text-zinc-200"
      >
        {initials}
      </button>
    </div>
  );
}
