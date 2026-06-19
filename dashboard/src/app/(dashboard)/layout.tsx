import { AppShell } from "@/components/layout/app-shell";
import { OrgProvider } from "@/components/layout/org-provider";
import { DEFAULT_ORG_SUMMARY, getOrgSummary } from "@/lib/auth";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const org = (await getOrgSummary()) ?? DEFAULT_ORG_SUMMARY;

  return (
    <OrgProvider org={org}>
      <AppShell>{children}</AppShell>
    </OrgProvider>
  );
}
