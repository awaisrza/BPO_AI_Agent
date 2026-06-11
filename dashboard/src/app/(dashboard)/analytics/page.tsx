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
        title="Pilot report — Medicare AEP"
        description="14-day performance summary for your BPO client."
        action={
          <Button variant="secondary">
            <Download className="h-4 w-4" />
            Export PDF
          </Button>
        }
      />

      <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Connect rate" value={`${stats.connectRate}%`} trend="up" />
        <StatCard label="Transfer rate" value={`${stats.transferRate}%`} trend="up" />
        <StatCard label="Avg duration" value={`${stats.avgDurationSec}s`} />
        <StatCard label="Cost per transfer" value={`$${stats.costPerTransfer}`} hint="vs $95 human" trend="up" />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Conversion funnel" description="Dials to transfer" />
          <CardBody className="space-y-5">
            {funnel.map((step, i) => (
              <div key={step.label}>
                <div className="mb-2 flex justify-between text-sm">
                  <span className="text-zinc-500">{step.label}</span>
                  <span className="tabular-nums text-zinc-200">{step.value.toLocaleString()}</span>
                </div>
                <div className="h-1 overflow-hidden rounded-full bg-white/[0.06]">
                  <div
                    className="h-full rounded-full bg-zinc-100"
                    style={{ width: `${(step.value / maxFunnel) * 100}%`, opacity: 1 - i * 0.12 }}
                  />
                </div>
              </div>
            ))}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Cost comparison" description="Per qualified transfer" />
          <CardBody>
            <div className="space-y-6">
              <div>
                <div className="mb-2 flex justify-between text-sm">
                  <span className="text-zinc-500">AI fronter</span>
                  <span className="font-medium tabular-nums text-emerald-400/90">${stats.costPerTransfer}</span>
                </div>
                <div className="h-1 overflow-hidden rounded-full bg-white/[0.06]">
                  <div className="h-full w-[19%] rounded-full bg-emerald-400/80" />
                </div>
              </div>
              <div>
                <div className="mb-2 flex justify-between text-sm">
                  <span className="text-zinc-500">Human fronter</span>
                  <span className="font-medium tabular-nums text-zinc-400">${stats.humanCostPerTransfer}</span>
                </div>
                <div className="h-1 overflow-hidden rounded-full bg-white/[0.06]">
                  <div className="h-full w-full rounded-full bg-zinc-600" />
                </div>
              </div>
              <p className="rounded-lg bg-emerald-500/[0.06] px-4 py-3 text-sm text-emerald-400/90">
                81% lower cost per qualified transfer vs human fronter
              </p>
            </div>
          </CardBody>
        </Card>
      </div>

      <Card className="mt-6">
        <CardHeader title="Operational metrics" />
        <CardBody>
          <div className="grid gap-8 sm:grid-cols-3">
            <Metric label="Avg active min / bot" value={stats.activeMinPerBot.toLocaleString()} />
            <Metric label="AMD drop rate" value="94%" />
            <Metric label="Pilot period" value="14 days" />
          </div>
        </CardBody>
      </Card>
    </>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-sm text-zinc-500">{label}</p>
      <p className="mt-2 text-xl font-semibold tracking-tight text-zinc-100">{value}</p>
    </div>
  );
}
