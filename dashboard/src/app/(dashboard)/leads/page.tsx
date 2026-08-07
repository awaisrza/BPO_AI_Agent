import { Download, RefreshCw, Search } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { StatCard } from "@/components/ui/stat-card";
import { Input, Select } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "@/components/ui/table";
import { leadSummary, leads } from "@/lib/mock-data";

function leadStatus(status: string) {
  const map: Record<string, "default" | "info" | "success" | "warning" | "danger"> = {
    new: "default",
    dialed: "info",
    qualified: "success",
    transferred: "success",
    not_interested: "danger",
    voicemail: "warning",
  };
  return (
    <Badge variant={map[status] ?? "default"}>
      {status.replace("_", " ")}
    </Badge>
  );
}

export default function LeadsPage() {
  return (
    <>
      <PageHeader
        title="Leads"
        description="Track dial outcomes synced from ViciDial."
        action={
          <>
            <Button variant="secondary">
              <Download className="h-4 w-4" />
              Import CSV
            </Button>
            <Button variant="secondary">
              <RefreshCw className="h-4 w-4" />
              Sync ViciDial
            </Button>
          </>
        }
      />

      <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <StatCard label="Total" value={leadSummary.total.toLocaleString()} />
        <StatCard label="Dialed" value={leadSummary.dialed.toLocaleString()} />
        <StatCard label="Qualified" value={leadSummary.qualified.toLocaleString()} />
        <StatCard label="Transferred" value={leadSummary.transferred.toLocaleString()} />
        <StatCard label="DNC" value={leadSummary.dnc} />
      </div>

      <Card>
        <CardHeader
          title="Medicare AEP leads"
          action={
            <div className="flex items-center gap-2">
              <Select className="py-1.5 text-xs">
                <option>All statuses</option>
                <option>Transferred</option>
                <option>Qualified</option>
              </Select>
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-zinc-600" />
                <Input placeholder="Search phone..." className="w-44 py-1.5 pl-8 text-xs" />
              </div>
            </div>
          }
        />
        <CardBody className="px-0 pb-0 pt-0">
          <Table>
            <TableHead>
              <TableHeaderCell>Phone</TableHeaderCell>
              <TableHeaderCell>Name</TableHeaderCell>
              <TableHeaderCell>Status</TableHeaderCell>
              <TableHeaderCell>Campaign</TableHeaderCell>
              <TableHeaderCell>Last attempt</TableHeaderCell>
              <TableHeaderCell>Outcome</TableHeaderCell>
            </TableHead>
            <TableBody>
              {leads.map((lead) => (
                <TableRow key={lead.phone}>
                  <TableCell className="font-mono text-zinc-300">{lead.phone}</TableCell>
                  <TableCell className="text-zinc-500">{lead.name}</TableCell>
                  <TableCell>{leadStatus(lead.status)}</TableCell>
                  <TableCell className="text-zinc-500">{lead.campaign}</TableCell>
                  <TableCell className="text-zinc-600">{lead.lastAttempt}</TableCell>
                  <TableCell className="text-zinc-500">{lead.outcome}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardBody>
      </Card>
    </>
  );
}
