import Image from "next/image";

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
      <div aria-hidden className="auth-shell-base pointer-events-none absolute inset-0" />
      <div aria-hidden className="auth-shell-glow pointer-events-none absolute inset-0" />

      <div className="relative z-10 mx-auto flex w-full max-w-[400px] flex-col items-center">
        <header className="auth-shell-brand mb-7 flex w-full flex-col items-center justify-center text-center sm:mb-8">
          <div className="flex w-full items-center justify-center">
            <Image
              src="/parasite-mark.png"
              alt=""
              width={230}
              height={330}
              className="auth-shell-mark mx-auto h-24 w-auto object-contain object-center sm:h-28"
              priority
            />
          </div>
          <p className="mt-4 w-full text-center font-[family-name:var(--font-auth-display)] text-3xl font-semibold tracking-[-0.04em] text-foreground sm:text-4xl">
            Parasite
          </p>
          {eyebrow ? (
            <p className="mt-2 text-caption font-medium uppercase tracking-[0.18em] text-foreground-faint">
              {eyebrow}
            </p>
          ) : null}
          <h1 className="sr-only">{title}</h1>
        </header>

        <main className="auth-shell-panel w-full">
          <div className="rounded-lg border border-surface-border bg-surface-raised px-5 py-6 sm:px-6 sm:py-7">
            <div className="mb-5 text-center">
              <p className="font-[family-name:var(--font-auth-display)] text-lg font-semibold tracking-tight text-foreground">
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
