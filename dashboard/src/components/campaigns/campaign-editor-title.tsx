"use client";

import { useEffect, useState } from "react";
import { getCampaignById } from "@/lib/campaigns";

const BUILTIN_TITLES: Record<string, string> = {
  "med-aep": "Medicare AEP v2",
  "solar-q1": "Solar intro",
  "debt-rem": "Debt v1",
};

export function CampaignEditorTitle({ id }: { id: string }) {
  const [title, setTitle] = useState(BUILTIN_TITLES[id] ?? "Campaign script");

  useEffect(() => {
    const campaign = getCampaignById(id);
    if (campaign) setTitle(campaign.script);
  }, [id]);

  return <>{title}</>;
}
