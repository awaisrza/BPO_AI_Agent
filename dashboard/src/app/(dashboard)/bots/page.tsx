import { Plus } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ProgressBar } from "@/components/ui/progress-bar";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "@/components/ui/table";
import { bots, org } from "@/lib/mock-data";

function botStatus(status: string) {
  const map: Record<string, { label: string; variant: "live" | "warning" | "info" | "default" }> = {
    live: { label: "On call", variant: "live" },
    ringing: { label: "Ringing", variant: "warning" },
    dialing: { label: "Dialing", variant: "info" },
    idle: { label: "Idle", variant: "default" },
  };
  const s = map[status] ?? map.idle;
  return <Badge variant={s.variant} dot={s.variant !== "default"}>{s.label}</Badge>;
}

export default function BotsPage() {
  return (
    <>
      <PageHeader
        title="Bot fleet"
        description="Each bot is one concurrent line. Assign bots to campaigns to start dialing."
        action={
          <Button variant="secondary">
            <Plus className="h-4 w-4" />
            Assign to campaign
          </Button>
        }
      />

      <Card className="mb-6">
        <CardBody>
          <ProgressBar
            value={org.botsActive}
            max={org.botsIncluded}
            label={`${org.plan} plan usage`}
            sublabel={`${org.botsIncluded - org.botsActive} available`}
          />
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="All bots" description="Live status across campaigns" />
        <CardBody className="px-0 pb-0 pt-0">
          <Table>
            <TableHead>
              <TableHeaderCell>Bot ID</TableHeaderCell>
              <TableHeaderCell>Campaign</TableHeaderCell>
              <TableHeaderCell>Status</TableHeaderCell>
              <TableHeaderCell className="text-right">Calls/hr</TableHeaderCell>
              <TableHeaderCell className="text-right">Active now</TableHeaderCell>
            </TableHead>
            <TableBody>
              {bots.map((bot) => (
                <TableRow key={bot.id}>
                  <TableCell className="font-medium text-zinc-200">{bot.id}</TableCell>
                  <TableCell className="text-zinc-500">{bot.campaign}</TableCell>
                  <TableCell>{botStatus(bot.status)}</TableCell>
                  <TableCell className="text-right tabular-nums text-zinc-500">{bot.callsPerHour || "—"}</TableCell>
                  <TableCell className="text-right font-mono text-zinc-400">{bot.activeNow}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardBody>
      </Card>
    </>
  );
}
