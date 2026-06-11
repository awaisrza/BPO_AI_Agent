"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";

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
      setError(
        err instanceof Error
          ? err.message
          : "Could not reach Supabase. Check .env.local and restart npm run dev.",
      );
      setLoading(false);
    }
  }

  return (
    <div className="rounded-xl border border-surface-border bg-surface-raised p-8">
      <div className="mb-8">
        <p className="text-xs font-medium uppercase tracking-wider text-zinc-600">AI Fronter</p>
        <h1 className="mt-2 text-xl font-semibold text-zinc-50">Create account</h1>
        <p className="mt-2 text-sm text-zinc-500">Set up your call center workspace.</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-5">
        <Field label="Company name">
          <Input
            value={orgName}
            onChange={(e) => setOrgName(e.target.value)}
            placeholder="ABC Call Center"
            required
          />
        </Field>

        <Field label="Your name">
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Ahmed"
            required
          />
        </Field>

        <Field label="Email">
          <Input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="admin@yourbpo.com"
            required
            autoComplete="email"
          />
        </Field>

        <Field label="Password">
          <Input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={8}
            required
            autoComplete="new-password"
          />
        </Field>

        {error && (
          <p className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
            {error}
          </p>
        )}

        <Button type="submit" className="w-full" disabled={loading}>
          {loading ? "Creating account…" : "Create account"}
        </Button>
      </form>

      <p className="mt-6 text-center text-sm text-zinc-500">
        Already have an account?{" "}
        <Link href="/login" className="text-zinc-300 hover:text-white">
          Sign in
        </Link>
      </p>
    </div>
  );
}
