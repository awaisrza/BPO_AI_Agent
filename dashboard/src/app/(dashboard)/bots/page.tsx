import { Plus } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { Button } from "@/components/ui/button";
import { BotsTable } from "@/components/bots/bots-table";
import { BotsUsage } from "@/components/bots/bots-usage";

export default function BotsPage() {
  return (
    <>
      <PageHeader
        title="Agent fleet"
        description="Assign agents to campaigns. Run the campaign to start all assigned agents."
        eyebrow="Management"
        action={
          <Button variant="secondary" href="/bots/assign">
            <Plus className="h-4 w-4" />
            Assign to campaign
          </Button>
        }
      />

      <BotsUsage />
      <BotsTable />
    </>
  );
}
