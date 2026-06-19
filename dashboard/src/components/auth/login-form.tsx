"use client";

import Link from "next/link";
import { useState } from "react";
import { createClient, supabaseConfigHelp } from "@/lib/supabase/client";
import { getOrgId } from "@/lib/get-org-id";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";

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
          setError("Confirm your email first. In Supabase → Authentication → Users → confirm your user.");
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
        setError("Sign-in succeeded but no session was created. Refresh the page and try again.");
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
      setError(
        err instanceof Error
          ? err.message
          : supabaseConfigHelp(),
      );
      setLoading(false);
    }
  }

  return (
    <div className="rounded-lg border border-surface-border bg-surface-raised p-6 sm:p-8">
      <div className="mb-6 border-b border-surface-border-subtle pb-6">
        <p className="data-label">AI Fronter</p>
        <h1 className="mt-2 text-xl font-semibold text-foreground">Sign in</h1>
        <p className="mt-1.5 text-body text-foreground-muted">Access your call center dashboard.</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
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
            required
            autoComplete="current-password"
          />
        </Field>

        {error && <p className="text-caption text-status-danger">{error}</p>}

        <Button type="submit" className="w-full" disabled={loading}>
          {loading ? "Signing in…" : "Sign in"}
        </Button>
      </form>

      <p className="mt-6 text-center text-caption text-foreground-muted">
        No account?{" "}
        <Link href="/signup" className="font-medium text-brand hover:text-brand-hover">
          Create one
        </Link>
      </p>
    </div>
  );
}
