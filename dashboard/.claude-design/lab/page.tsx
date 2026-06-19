import { VariantA } from "./variants/VariantA";
import { VariantB } from "./variants/VariantB";
import { VariantC } from "./variants/VariantC";
import { VariantD } from "./variants/VariantD";
import { VariantE } from "./variants/VariantE";

const variants = [
  { id: "A", title: "Stripe sidebar", rationale: "Elevated nav, grouped sections — pattern for all pages.", Component: VariantA },
  { id: "B", title: "Icon rail", rationale: "Max content width; shell scales to data-heavy pages.", Component: VariantB },
  { id: "C", title: "Top navigation", rationale: "Horizontal tabs — strong mobile / both-context fit.", Component: VariantC },
  { id: "D", title: "Context panel", rationale: "Persistent live-status rail alongside any page content.", Component: VariantD },
  { id: "E", title: "Premium spacious", rationale: "Generous spacing and softer surfaces — premium brand.", Component: VariantE },
] as const;

export function DesignLabContent() {
  return (
    <div className="min-h-screen bg-surface">
      <header className="border-b border-surface-border bg-surface-raised px-6 py-5">
        <p className="data-label">Design Lab</p>
        <h1 className="mt-1 text-xl font-semibold text-foreground">Full Dashboard UI — 5 Shell Patterns</h1>
        <p className="mt-2 max-w-2xl text-body text-foreground-muted">
          New design for all pages. Each variant shows app shell + Overview content as the template for Campaigns, Bots, Settings, etc.
        </p>
        <p className="mt-3 text-caption text-foreground-muted">
          Individual previews:{" "}
          {variants.map(({ id, title }, i) => (
            <span key={id}>
              {i > 0 && " · "}
              <a href={`/design-lab/${id.toLowerCase()}`} className="text-brand hover:underline">
                {id} — {title}
              </a>
            </span>
          ))}
        </p>
      </header>
      <main className="space-y-12 px-6 py-8">
        {variants.map(({ id, title, rationale, Component }) => (
          <section key={id} className="space-y-3">
            <div className="flex items-baseline gap-3">
              <span className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-brand-muted text-caption font-semibold text-brand">{id}</span>
              <div>
                <h2 className="text-body font-semibold text-foreground">{title}</h2>
                <p className="text-caption text-foreground-muted">{rationale}</p>
              </div>
            </div>
            <div data-variant={id}>
              <Component />
            </div>
          </section>
        ))}
      </main>
    </div>
  );
}
