import Link from "next/link";
import { Plus } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { Button } from "@/components/ui/button";
import { CampaignsTable } from "@/components/campaigns/campaigns-table";

export default function CampaignsPage() {
  return (
    <>
      <PageHeader
        title="Campaigns"
        description="Manage outbound campaigns, scripts, and bot assignments."
        action={
          <Link href="/campaigns/new">
            <Button>
              <Plus className="h-4 w-4" />
              New campaign
            </Button>
          </Link>
        }
      />

      <CampaignsTable />
    </>
  );
}
