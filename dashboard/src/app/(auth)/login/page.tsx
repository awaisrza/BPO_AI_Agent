import { Suspense } from "react";
import { AuthShell } from "@/components/auth/auth-shell";
import { LoginForm } from "@/components/auth/login-form";

export default function LoginPage() {
  return (
    <AuthShell
      title="Sign in"
      description="Access your AI voice agent operations console."
    >
      <Suspense
        fallback={
          <p className="text-body text-foreground-faint">Loading…</p>
        }
      >
        <LoginForm />
      </Suspense>
    </AuthShell>
  );
}
