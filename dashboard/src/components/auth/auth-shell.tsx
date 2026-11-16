import Image from "next/image";
import { AuthAtmosphere } from "@/components/auth/auth-atmosphere";

export function AuthShell({
  children,
  eyebrow,
  title,
  description,
}: {
  children: React.ReactNode;
  eyebrow?: string;
  title: string;
  description: string;
}) {
  return (
    <div className="auth-shell relative flex min-h-[100dvh] items-center justify-center overflow-hidden px-4 py-10 text-foreground">
      <AuthAtmosphere />

      <div className="relative z-10 mx-auto flex w-full max-w-[420px] flex-col items-center">
        <header className="auth-shell-brand mb-7 flex w-full flex-col items-center justify-center text-center sm:mb-8">
          <div className="flex w-full items-center justify-center">
            <Image
              src="/parasite-mark.png"
              alt=""
              width={230}
              height={330}
              className="auth-shell-mark mx-auto h-28 w-auto object-contain object-center drop-shadow-[0_16px_48px_rgba(59,130,246,0.35)] sm:h-32"
              priority
            />
          </div>
          <p className="mt-5 w-full text-center font-[family-name:var(--font-auth-display)] text-4xl font-semibold tracking-[-0.04em] text-foreground sm:text-5xl">
            Parasite
          </p>
          {eyebrow ? (
            <p className="mt-3 text-caption font-medium uppercase tracking-[0.18em] text-foreground-faint">
              {eyebrow}
            </p>
          ) : null}
          <h1 className="sr-only">{title}</h1>
        </header>

        <main className="auth-shell-panel w-full">
          <div className="rounded-lg border border-surface-border bg-surface-raised/95 px-5 py-6 shadow-sm backdrop-blur-sm sm:px-7 sm:py-8">
            <div className="mb-5 text-center">
              <p className="font-[family-name:var(--font-auth-display)] text-xl font-semibold tracking-tight text-foreground">
                {title}
              </p>
              <p className="mt-1.5 text-caption leading-5 text-foreground-muted">
                {description}
              </p>
            </div>
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
