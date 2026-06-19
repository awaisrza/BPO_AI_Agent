import { FeedbackOverlay } from "./FeedbackOverlay";
import VariantA from "../../../.claude-design/lab/variants/VariantA";
import VariantB from "../../../.claude-design/lab/variants/VariantB";
import VariantC from "../../../.claude-design/lab/variants/VariantC";
import VariantD from "../../../.claude-design/lab/variants/VariantD";
import VariantE from "../../../.claude-design/lab/variants/VariantE";

const variants = [
  {
    id: "A",
    title: "Hierarchy focus",
    rationale: "One hero KPI (transfer rate) dominates; secondary metrics and live sessions support it.",
    Component: VariantA,
  },
  {
    id: "B",
    title: "Top navigation",
    rationale: "Horizontal nav replaces sidebar — command-center layout, full-width content.",
    Component: VariantB,
  },
  {
    id: "C",
    title: "Compact density",
    rationale: "Inline stat strip and dense table — more data visible at a glance.",
    Component: VariantC,
  },
  {
    id: "D",
    title: "Split-pane + expand",
    rationale: "Activity feed with expandable rows and a persistent detail pane.",
    Component: VariantD,
  },
  {
    id: "E",
    title: "Premium Stripe",
    rationale: "Spacious, refined surfaces with subtle rings and gradient accents.",
    Component: VariantE,
  },
] as const;

export default function DesignLabPage() {
  return (
    <div className="min-h-screen bg-surface">
      <header className="border-b border-surface-border bg-surface-raised px-6 py-8">
        <p className="text-2xs font-medium uppercase tracking-wider text-brand">Design Lab</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
          Full Dashboard UI — 5 Variations
        </h1>
        <p className="mt-2 max-w-3xl text-body text-foreground-muted">
          Redesign scope: app shell + Overview page as the pattern for all dashboard pages.
          Premium · Stripe-inspired · comfortable density · dark mode · ops manager persona.
        </p>
        <div className="mt-4 flex flex-wrap gap-2 text-caption text-foreground-faint">
          <span className="rounded-md bg-surface-overlay px-2 py-1">Pain point: outdated look</span>
          <span className="rounded-md bg-surface-overlay px-2 py-1">Keep existing copy</span>
          <span className="rounded-md bg-surface-overlay px-2 py-1">Use existing components</span>
        </div>
      </header>

      <main className="mx-auto max-w-[1400px] space-y-10 px-4 py-8 sm:px-6 lg:px-8">
        <p className="text-body text-foreground-muted">
          Review each variant below. Use the feedback button (bottom-right) to click elements and leave comments,
          or tell me your preferences in chat.
        </p>

        {variants.map(({ id, title, rationale, Component }) => (
          <section key={id} data-variant={id} className="scroll-mt-8">
            <div className="mb-3 flex items-baseline gap-3">
              <span className="flex h-8 w-8 items-center justify-center rounded-md bg-brand-muted text-body font-bold text-brand">
                {id}
              </span>
              <div>
                <h2 className="text-body font-semibold text-foreground">{title}</h2>
                <p className="text-caption text-foreground-muted">{rationale}</p>
              </div>
            </div>
            <Component />
          </section>
        ))}
      </main>

      <FeedbackOverlay targetName="Full Dashboard UI" />
    </div>
  );
}
