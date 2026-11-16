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
    <div className="auth-shell relative flex min-h-screen items-center justify-center overflow-hidden px-4 py-10 text-white sm:justify-start sm:px-10 lg:px-16 xl:px-24">
      {/* Discord-inspired deep indigo field */}
      <div aria-hidden className="auth-shell-base pointer-events-none absolute inset-0" />
      <div aria-hidden className="auth-shell-wash pointer-events-none absolute inset-0" />
      <div aria-hidden className="auth-shell-stars pointer-events-none absolute inset-0" />

      {/* Soft floating orbs — Discord-style ambient motion */}
      <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
        <span className="auth-orb auth-orb-a" />
        <span className="auth-orb auth-orb-b" />
        <span className="auth-orb auth-orb-c" />
        <span className="auth-orb auth-orb-d" />
        <span className="auth-float auth-float-1" />
        <span className="auth-float auth-float-2" />
        <span className="auth-float auth-float-3" />
      </div>

      <div className="relative z-10 flex w-full max-w-[420px] flex-col items-stretch sm:items-start">
        <header className="auth-shell-brand mb-7 flex w-full flex-col items-center text-center sm:mb-8 sm:items-start sm:text-left">
          <Image
            src="/parasite-mark.png"
            alt=""
            width={128}
            height={128}
            className="h-28 w-28 object-contain drop-shadow-[0_18px_50px_rgba(88,101,242,0.45)] sm:h-32 sm:w-32"
            priority
          />
          <p className="mt-5 font-[family-name:var(--font-auth-display)] text-4xl font-semibold tracking-[-0.04em] text-white sm:text-5xl">
            Parasite
          </p>
          {eyebrow ? (
            <p className="mt-3 text-caption font-medium uppercase tracking-[0.18em] text-white/55">
              {eyebrow}
            </p>
          ) : null}
          <h1 className="sr-only">{title}</h1>
        </header>

        <main className="auth-shell-panel w-full">
          <div className="rounded-lg bg-[#313338] px-5 py-6 shadow-[0_8px_32px_rgba(0,0,0,0.35)] sm:px-7 sm:py-8">
            <div className="mb-5">
              <p className="text-xl font-semibold tracking-tight text-white">{title}</p>
              <p className="mt-1.5 text-caption leading-5 text-[#b5bac1]">
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
