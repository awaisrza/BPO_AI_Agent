import { PageHeader } from "@/components/ui/page-header";
import { StatCard } from "@/components/ui/stat-card";
import { Card } from "@/components/ui/card";

export default function OverviewPage() {
  return (
    <div>
      <PageHeader
        title="Overview"
        description="Monitor your AI voice agents, call volume, and campaign performance."
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Calls today" value="—" />
        <StatCard label="Active agents" value="—" />
        <StatCard label="Conversion rate" value="—" />
        <StatCard label="Avg. handle time" value="—" />
      </div>

      <Card className="mt-6 p-6">
        <p className="text-body text-foreground-muted">
          Connect your Supabase project and deploy agents to see live metrics here.
        </p>
      </Card>
    </div>
  );
}
