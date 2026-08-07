import { notFound } from "next/navigation";
import { FeedbackOverlay } from "../FeedbackOverlay";
import { VariantA } from "../../../../.claude-design/lab/variants/VariantA";
import { VariantB } from "../../../../.claude-design/lab/variants/VariantB";
import { VariantC } from "../../../../.claude-design/lab/variants/VariantC";
import { VariantD } from "../../../../.claude-design/lab/variants/VariantD";
import { VariantE } from "../../../../.claude-design/lab/variants/VariantE";

const variants = {
  a: { id: "A", title: "Stripe sidebar", Component: VariantA },
  b: { id: "B", title: "Icon rail", Component: VariantB },
  c: { id: "C", title: "Top navigation", Component: VariantC },
  d: { id: "D", title: "Context panel", Component: VariantD },
  e: { id: "E", title: "Premium spacious", Component: VariantE },
} as const;

export function generateStaticParams() {
  return Object.keys(variants).map((variant) => ({ variant }));
}

export default async function DesignLabVariantPage({
  params,
}: {
  params: Promise<{ variant: string }>;
}) {
  const { variant } = await params;
  const entry = variants[variant.toLowerCase() as keyof typeof variants];
  if (!entry) notFound();

  const { id, title, Component } = entry;

  return (
    <div className="min-h-screen bg-surface p-6">
      <p className="mb-4 text-caption text-foreground-muted">
        <a href="/design-lab" className="text-brand hover:underline">← All variants</a>
        {" · "}Variant {id}: {title}
      </p>
      <div data-variant={id}>
        <Component />
      </div>
      <FeedbackOverlay targetName="FullDashboardUI" variants={[id as "A" | "B" | "C" | "D" | "E"]} />
    </div>
  );
}
