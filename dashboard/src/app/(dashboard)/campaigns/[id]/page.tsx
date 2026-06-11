import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { CampaignEditorForm } from "@/components/campaigns/campaign-editor-form";

export default async function CampaignEditorPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <>
      <Link
        href="/campaigns"
        className="mb-6 inline-flex items-center gap-1.5 text-sm text-zinc-600 transition-colors hover:text-zinc-400"
      >
        <ArrowLeft className="h-4 w-4" />
        Campaigns
      </Link>

      <CampaignEditorForm id={id} />
    </>
  );
}
