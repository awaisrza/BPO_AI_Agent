import { Download } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { StatCard } from "@/components/ui/stat-card";
import { funnel, stats } from "@/lib/mock-data";

export default function AnalyticsPage() {
  const maxFunnel = funnel[0].value;

  return (
    <>
      <PageHeader
        title="Analytics"
        description="Campaign performance summary and cost efficiency metrics."
        eyebrow="Reporting"
        action={
          <Button variant="secondary">
            <Download className="h-4 w-4" />
            Export PDF
          </Button>
        }
      />

      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Connect rate" value={`${stats.connectRate}%`} trend="up" />
        <StatCard label="Transfer rate" value={`${stats.transferRate}%`} trend="up" />
        <StatCard label="Avg duration" value={`${stats.avgDurationSec}s`} />
        <StatCard label="Cost per transfer" value={`$${stats.costPerTransfer}`} hint="vs $95 human" trend="up" />
      </div>

      <Card>
        <CardHeader title="Conversion funnel" description="Dials to qualified transfer" />
        <CardBody className="space-y-4">
          {funnel.map((step, i) => (
            <div key={step.label}>
              <div className="mb-1.5 flex justify-between text-body">
                <span className="text-foreground-muted">{step.label}</span>
                <span className="tabular-nums font-medium text-foreground">{step.value.toLocaleString()}</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-sm bg-surface-overlay">
                <div
                  className="h-full rounded-sm bg-brand transition-all"
                  style={{ width: `${(step.value / maxFunnel) * 100}%`, opacity: 1 - i * 0.1 }}
                />
              </div>
            </div>
          ))}
        </CardBody>
      </Card>

      <Card className="mt-4">
        <CardHeader title="Operational metrics" />
        <CardBody>
          <div className="grid gap-6 sm:grid-cols-3">
            <Metric label="Avg active min / agent" value={stats.activeMinPerBot.toLocaleString()} />
            <Metric label="AMD drop rate" value="94%" />
            <Metric label="Reporting period" value="14 days" />
          </div>
        </CardBody>
      </Card>
    </>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="data-label">{label}</p>
      <p className="metric-value mt-2">{value}</p>
    </div>
  );
}
