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
    <div className="auth-shell relative flex min-h-screen items-center justify-center overflow-hidden bg-surface px-4 py-10 text-foreground sm:px-6">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_90%_55%_at_50%_40%,rgba(59,130,246,0.2),transparent_60%)]"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_85%_90%,rgba(59,130,246,0.08),transparent_42%)]"
      />
      <div
        aria-hidden
        className="auth-shell-grid pointer-events-none absolute inset-0 opacity-[0.35]"
      />

      <div className="relative z-10 flex w-full max-w-md flex-col items-center">
        <header className="auth-shell-brand mb-8 flex w-full flex-col items-center text-center sm:mb-10">
          <Image
            src="/parasite-mark.png"
            alt=""
            width={128}
            height={128}
            className="mx-auto h-28 w-28 object-contain drop-shadow-[0_16px_48px_rgba(59,130,246,0.3)] sm:h-32 sm:w-32"
            priority
          />
          <p className="mt-6 font-[family-name:var(--font-auth-display)] text-4xl font-semibold tracking-[-0.04em] text-foreground sm:text-5xl">
            Parasite
          </p>
          {eyebrow ? (
            <p className="mt-3 text-caption font-medium uppercase tracking-[0.18em] text-foreground-faint">
              {eyebrow}
            </p>
          ) : null}
          <h1 className="sr-only">{title}</h1>
          <p className="mt-3 max-w-sm text-body text-foreground-muted sm:text-[0.9375rem] sm:leading-6">
            {description}
          </p>
        </header>

        <main className="auth-shell-panel w-full">
          <div className="rounded-lg border border-surface-border/80 bg-surface-raised/80 px-5 py-6 backdrop-blur-sm sm:px-6 sm:py-7">
            <div className="mb-5 flex items-baseline justify-between gap-3 border-b border-surface-border-subtle pb-4">
              <p className="text-[15px] font-semibold tracking-tight text-foreground">
                {title}
              </p>
              <p className="text-caption text-foreground-faint">Operations</p>
            </div>
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
