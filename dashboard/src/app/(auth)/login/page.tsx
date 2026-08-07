import { Suspense } from "react";
import { LoginForm } from "@/components/auth/login-form";

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="text-sm text-zinc-500">Loading…</div>}>
      <div className="w-full max-w-lg">
        <LoginForm />
      </div>
    </Suspense>
  );
}
