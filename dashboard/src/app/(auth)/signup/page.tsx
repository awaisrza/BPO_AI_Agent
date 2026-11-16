import { AuthShell } from "@/components/auth/auth-shell";
import { SignupForm } from "@/components/auth/signup-form";

export default function SignupPage() {
  return (
    <AuthShell
      title="Create account"
      description="Stand up a Parasite workspace for your agent fleet."
    >
      <SignupForm />
    </AuthShell>
  );
}
