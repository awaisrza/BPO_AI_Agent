import { PageBack } from "@/components/ui/page-back";
import { CampaignEditorForm } from "@/components/campaigns/campaign-editor-form";

export default async function CampaignEditorPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <>
      <PageBack href="/campaigns" label="Campaigns" />
      <CampaignEditorForm id={id} />
    </>
  );
}
