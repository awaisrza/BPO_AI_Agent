"use client";

import { useState } from "react";
import { PageHeader } from "@/components/ui/page-header";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs } from "@/components/ui/tabs";
import { Field, Input, Checkbox } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "@/components/ui/table";
import { users } from "@/lib/mock-data";

const tabs = ["Organization", "Users", "Compliance"] as const;

export default function SettingsPage() {
  const [tab, setTab] = useState<(typeof tabs)[number]>("Organization");

  return (
    <>
      <PageHeader
        title="Settings"
        description="Organization profile, team access, and compliance rules."
      />

      <Tabs tabs={tabs} active={tab} onChange={setTab} />

      {tab === "Organization" && (
        <Card>
          <CardHeader title="Organization" />
          <CardBody className="max-w-md space-y-5">
            <Field label="Company name">
              <Input defaultValue="ABC Call Center" />
            </Field>
            <Field label="Timezone">
              <Input defaultValue="US Eastern (ET)" />
            </Field>
            <Field label="Calling hours">
              <Input defaultValue="9:00 AM – 8:00 PM" />
            </Field>
            <Checkbox
              label="Enforce PTA telemarketing rules (consent and calling hours)"
              defaultChecked
            />
            <Button className="mt-2">Save changes</Button>
          </CardBody>
        </Card>
      )}

      {tab === "Users" && (
        <Card>
          <CardHeader title="Team members" action={<Button variant="secondary" size="sm">Invite user</Button>} />
          <CardBody className="px-0 pb-0 pt-0">
            <Table>
              <TableHead>
                <TableHeaderCell>Name</TableHeaderCell>
                <TableHeaderCell>Email</TableHeaderCell>
                <TableHeaderCell>Role</TableHeaderCell>
              </TableHead>
              <TableBody>
                {users.map((u) => (
                  <TableRow key={u.email}>
                    <TableCell className="font-medium text-zinc-200">{u.name}</TableCell>
                    <TableCell className="text-zinc-500">{u.email}</TableCell>
                    <TableCell className="text-zinc-500">{u.role}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardBody>
        </Card>
      )}

      {tab === "Compliance" && (
        <Card>
          <CardHeader title="Compliance" description="DNC, consent, and recording retention" />
          <CardBody className="max-w-md space-y-5">
            <Field label="Do-not-call list">
              <Button variant="secondary">Upload DNC CSV</Button>
            </Field>
            <Checkbox label="Require consent before outbound dial" defaultChecked />
            <Field label="Call recording retention">
              <Input defaultValue="7 days" />
            </Field>
            <Button>Save changes</Button>
          </CardBody>
        </Card>
      )}
    </>
  );
}
