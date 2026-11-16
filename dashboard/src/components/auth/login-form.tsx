"use client";

import Link from "next/link";
import { useState } from "react";
import { createClient, supabaseConfigHelp } from "@/lib/supabase/client";
import { getOrgId } from "@/lib/get-org-id";
import { cn } from "@/lib/utils";

const fieldClass =
  "w-full rounded-[3px] border-0 bg-[#1e1f22] px-3 text-body text-[#dbdee1] outline-none ring-0 transition-[box-shadow,background-color] placeholder:text-[#6d6f78] focus:bg-[#1e1f22] focus:shadow-[0_0_0_1px_#5865f2] disabled:opacity-50";

export function LoginForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const supabase = createClient();
      const { error: signInError } = await supabase.auth.signInWithPassword({
        email: email.trim(),
        password,
      });

      if (signInError) {
        const message = signInError.message.toLowerCase();
        if (message.includes("email not confirmed")) {
          setError(
            "Confirm your email first. In Supabase → Authentication → Users → confirm your user.",
          );
        } else if (message.includes("invalid login credentials")) {
          setError("Wrong email or password. Try again or create a new account.");
        } else {
          setError(signInError.message);
        }
        setLoading(false);
        return;
      }

      const {
        data: { session },
      } = await supabase.auth.getSession();

      if (!session) {
        setError(
          "Sign-in succeeded but no session was created. Refresh the page and try again.",
        );
        setLoading(false);
        return;
      }

      try {
        await getOrgId(supabase);
      } catch {
        // Workspace not ready — dashboard layout will show setup page
      }

      window.location.assign("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : supabaseConfigHelp());
      setLoading(false);
    }
  }

  return (
    <>
      <form onSubmit={handleSubmit} className="space-y-4">
        <label className="block space-y-1.5">
          <span className="text-[11px] font-bold uppercase tracking-wide text-[#b5bac1]">
            Email
          </span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
            required
            autoComplete="email"
            className={cn(fieldClass, "h-10")}
          />
        </label>

        <label className="block space-y-1.5">
          <span className="text-[11px] font-bold uppercase tracking-wide text-[#b5bac1]">
            Password
          </span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
            className={cn(fieldClass, "h-10")}
          />
        </label>

        {error ? <p className="text-caption text-[#f23f43]">{error}</p> : null}

        <button
          type="submit"
          disabled={loading}
          className="mt-2 flex h-11 w-full items-center justify-center rounded-[3px] bg-[#5865f2] text-[15px] font-medium text-white transition-colors hover:bg-[#4752c4] disabled:opacity-50"
        >
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>

      <p className="mt-5 text-caption text-[#949ba4]">
        No account?{" "}
        <Link href="/signup" className="text-[#00a8fc] hover:underline">
          Create one
        </Link>
      </p>
    </>
  );
}
