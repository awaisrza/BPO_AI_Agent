"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { createClient, supabaseConfigHelp } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

const fieldClass =
  "w-full rounded-[3px] border-0 bg-[#1e1f22] px-3 text-body text-[#dbdee1] outline-none ring-0 transition-[box-shadow,background-color] placeholder:text-[#6d6f78] focus:bg-[#1e1f22] focus:shadow-[0_0_0_1px_#5865f2] disabled:opacity-50";

export function SignupForm() {
  const router = useRouter();
  const [orgName, setOrgName] = useState("");
  const [name, setName] = useState("");
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
      const { data, error: signUpError } = await supabase.auth.signUp({
        email,
        password,
        options: {
          data: {
            org_name: orgName,
            name,
          },
        },
      });

      if (signUpError) {
        setError(signUpError.message);
        setLoading(false);
        return;
      }

      if (data.session) {
        router.push("/");
        router.refresh();
        return;
      }

      setError("Check your email to confirm your account, then sign in.");
      setLoading(false);
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
            Company name
          </span>
          <input
            value={orgName}
            onChange={(e) => setOrgName(e.target.value)}
            placeholder="Your BPO"
            required
            className={cn(fieldClass, "h-10")}
          />
        </label>

        <label className="block space-y-1.5">
          <span className="text-[11px] font-bold uppercase tracking-wide text-[#b5bac1]">
            Your name
          </span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Ahmed"
            required
            className={cn(fieldClass, "h-10")}
          />
        </label>

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
            minLength={8}
            required
            autoComplete="new-password"
            className={cn(fieldClass, "h-10")}
          />
        </label>

        {error ? <p className="text-caption text-[#f23f43]">{error}</p> : null}

        <button
          type="submit"
          disabled={loading}
          className="mt-2 flex h-11 w-full items-center justify-center rounded-[3px] bg-[#5865f2] text-[15px] font-medium text-white transition-colors hover:bg-[#4752c4] disabled:opacity-50"
        >
          {loading ? "Creating account…" : "Create account"}
        </button>
      </form>

      <p className="mt-5 text-caption text-[#949ba4]">
        Already have an account?{" "}
        <Link href="/login" className="text-[#00a8fc] hover:underline">
          Sign in
        </Link>
      </p>
    </>
  );
}
