import {
  Activity,
  ArrowRightLeft,
  Bot,
  Clock,
  DollarSign,
} from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { StatCard } from "@/components/ui/stat-card";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "@/components/ui/table";
import { liveCalls, org, stats, transferTrend } from "@/lib/mock-data";

function statusBadge(status: string) {
  if (status === "live") return <Badge variant="live" dot>Live</Badge>;
  if (status === "ringing") return <Badge variant="warning" dot>Ringing</Badge>;
  return <Badge variant="info" dot>Dialing</Badge>;
}

export default function DashboardPage() {
  const maxRate = Math.max(...transferTrend.map((d) => d.rate), 1);

  return (
    <>
      <PageHeader
        title={org.name}
        description="Real-time overview of your AI fronter fleet and campaign performance."
        eyebrow="Dashboard"
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <StatCard label="Active bots" value={org.botsActive} icon={Bot} hint={`of ${org.botsIncluded} included`} />
        <StatCard label="Calls today" value={stats.callsToday.toLocaleString()} icon={Activity} hint="+12% vs yesterday" trend="up" />
        <StatCard label="Transfer rate" value={`${stats.transferRate}%`} icon={ArrowRightLeft} hint="Qualified to closer" trend="up" />
        <StatCard label="Avg duration" value={`${stats.avgDurationSec}s`} icon={Clock} />
        <StatCard label="Cost today" value={`$${stats.costTodayUsd}`} icon={DollarSign} hint="Pilot estimate" />
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader title="Live calls" description="Bots on active sessions" />
          <CardBody className="px-0 pb-0 pt-0">
            <Table>
              <TableHead>
                <TableHeaderCell>Bot</TableHeaderCell>
                <TableHeaderCell>Campaign</TableHeaderCell>
                <TableHeaderCell>Status</TableHeaderCell>
                <TableHeaderCell className="text-right">Duration</TableHeaderCell>
              </TableHead>
              <TableBody>
                {liveCalls.map((call) => (
                  <TableRow key={call.bot}>
                    <TableCell className="font-medium text-zinc-200">{call.bot}</TableCell>
                    <TableCell className="text-zinc-500">{call.campaign}</TableCell>
                    <TableCell>{statusBadge(call.status)}</TableCell>
                    <TableCell className="text-right font-mono text-zinc-500">{call.duration}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardBody>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader title="Transfer rate" description="Last 7 days" />
          <CardBody>
            <div className="flex h-36 items-end gap-3">
              {transferTrend.map((d) => (
                <div key={d.day} className="flex flex-1 flex-col items-center gap-2">
                  <div
                    className="w-full rounded-sm bg-zinc-100/80 transition-all"
                    style={{ height: `${(d.rate / maxRate) * 100}px`, minHeight: d.rate ? 4 : 2 }}
                    title={`${d.rate}%`}
                  />
                  <span className="text-2xs text-zinc-600">{d.day}</span>
                </div>
              ))}
            </div>
            <p className="mt-6 text-xs text-zinc-600">
              Target: 15% transfer rate for pilot success
            </p>
          </CardBody>
        </Card>
      </div>
    </>
  );
}
