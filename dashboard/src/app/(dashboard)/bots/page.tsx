import Link from "next/link";
import { Plus } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { Button } from "@/components/ui/button";
import { BotsTable } from "@/components/bots/bots-table";
import { BotsUsage } from "@/components/bots/bots-usage";

export default function BotsPage() {
  return (
    <>
      <PageHeader
        title="Bot fleet"
        description="Each bot is one concurrent line. Assign bots to campaigns to start dialing."
        action={
          <Link href="/bots/assign">
            <Button variant="secondary">
              <Plus className="h-4 w-4" />
              Assign to campaign
            </Button>
          </Link>
        }
      />

      <BotsUsage />
      <BotsTable />
    </>
  );
}
