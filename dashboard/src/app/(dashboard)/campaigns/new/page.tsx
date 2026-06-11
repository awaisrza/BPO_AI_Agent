import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { Card, CardBody } from "@/components/ui/card";
import { NewCampaignForm } from "@/components/campaigns/new-campaign-form";

export default function NewCampaignPage() {
  return (
    <>
      <Link
        href="/campaigns"
        className="mb-6 inline-flex items-center gap-1.5 text-sm text-zinc-600 transition-colors hover:text-zinc-400"
      >
        <ArrowLeft className="h-4 w-4" />
        Campaigns
      </Link>

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
