import { PageBack } from "@/components/ui/page-back";
import { PageHeader } from "@/components/ui/page-header";
import { Card, CardBody } from "@/components/ui/card";
import { NewCampaignForm } from "@/components/campaigns/new-campaign-form";

export default function NewCampaignPage() {
  return (
    <>
      <PageBack href="/campaigns" label="Campaigns" />

      <PageHeader
        title="New campaign"
        description="Create an outbound campaign and configure its script next."
      />

      <Card>
        <CardBody>
          <NewCampaignForm />
        </CardBody>
      </Card>
    </>
  );
}
