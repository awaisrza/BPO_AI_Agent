"use client";

import { useState } from "react";
import { PageHeader } from "@/components/ui/page-header";
import { Tabs } from "@/components/ui/tabs";
import { OrganizationSettingsForm } from "@/components/settings/organization-settings-form";
import { UsersSettingsTable } from "@/components/settings/users-settings-table";
import { ComplianceSettingsForm } from "@/components/settings/compliance-settings-form";

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

      {tab === "Organization" && <OrganizationSettingsForm />}
      {tab === "Users" && <UsersSettingsTable />}
      {tab === "Compliance" && <ComplianceSettingsForm />}
    </>
  );
}
