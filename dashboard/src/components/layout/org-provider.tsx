"use client";

import { createContext, useContext } from "react";
import type { OrgSummary } from "@/lib/auth";

const OrgContext = createContext<OrgSummary | null>(null);

export function OrgProvider({
  org,
  children,
}: {
  org: OrgSummary;
  children: React.ReactNode;
}) {
  return <OrgContext.Provider value={org}>{children}</OrgContext.Provider>;
}

export function useOrg(): OrgSummary {
  const org = useContext(OrgContext);
  if (!org) {
    throw new Error("useOrg must be used within OrgProvider");
  }
  return org;
}
