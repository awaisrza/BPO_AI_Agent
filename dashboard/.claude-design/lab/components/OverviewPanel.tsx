import { Activity, ArrowRightLeft, Bot, Clock, DollarSign } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { StatCard } from "@/components/ui/stat-card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "@/components/ui/table";
import { liveCalls, org, stats } from "../data/fixtures";

function statusBadge(status: string) {
  if (status === "live") return <Badge variant="live" dot>Live</Badge>;
  if (status === "ringing") return <Badge variant="warning" dot>Ringing</Badge>;
  return <Badge variant="info" dot>Dialing</Badge>;
}

/** Shared overview content — same data across all shell variants */
export function OverviewPanel() {
  return (
    <div className="space-y-4 p-6">
      <div>
        <p className="data-label">Operations</p>
        <h2 className="text-xl font-semibold text-foreground">{org.name}</h2>
        <p className="mt-1 text-body text-foreground-muted">
          Fleet performance, live sessions, and transfer metrics.
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <StatCard label="Active agents" value={org.botsActive} icon={Bot} hint={`of ${org.botsIncluded} included`} />
        <StatCard label="Calls today" value={stats.callsToday.toLocaleString()} icon={Activity} hint="+12% vs yesterday" trend="up" />
        <StatCard label="Transfer rate" value={`${stats.transferRate}%`} icon={ArrowRightLeft} trend="up" />
        <StatCard label="Avg duration" value={`${stats.avgDurationSec}s`} icon={Clock} />
        <StatCard label="Est. cost today" value={`$${stats.costTodayUsd}`} icon={DollarSign} hint="Pilot estimate" />
      </div>
      <Card>
        <CardHeader title="Live sessions" description={`${liveCalls.length} agents currently on calls`} />
        <CardBody className="px-0 pb-0 pt-0">
          <Table>
            <TableHead>
              <TableHeaderCell>Agent</TableHeaderCell>
              <TableHeaderCell>Campaign</TableHeaderCell>
              <TableHeaderCell>Status</TableHeaderCell>
              <TableHeaderCell className="text-right">Duration</TableHeaderCell>
            </TableHead>
            <TableBody>
              {liveCalls.map((call) => (
                <TableRow key={call.bot}>
                  <TableCell className="font-medium">{call.bot}</TableCell>
                  <TableCell className="text-foreground-muted">{call.campaign}</TableCell>
                  <TableCell>{statusBadge(call.status)}</TableCell>
                  <TableCell className="text-right font-mono text-caption">{call.duration}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardBody>
      </Card>
    </div>
  );
}
