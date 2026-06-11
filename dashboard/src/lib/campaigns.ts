import type { CampaignRow, CampaignStatus } from "@/lib/types/database";
import { DEFAULT_SCRIPT_JSON } from "@/lib/types/database";

export type CampaignListItem = {
  id: string;
  name: string;
  script: string;
  bots: number;
  status: CampaignStatus;
  dials: number;
  transferRate: number;
};

export function scriptDisplayName(row: CampaignRow): string {
  return row.script_json?.label ?? `${row.name} v1`;
}

export function toListItem(row: CampaignRow, botCount = 0): CampaignListItem {
  return {
    id: row.id,
    name: row.name,
    script: scriptDisplayName(row),
    bots: botCount,
    status: row.status,
    dials: row.dials ?? 0,
    transferRate: Number(row.transfer_rate ?? 0),
  };
}

export function buildNewCampaignPayload(input: {
  orgId: string;
  name: string;
  scriptLabel?: string;
  status?: CampaignStatus;
}) {
  const label = input.scriptLabel?.trim() || `${input.name.trim()} v1`;
  return {
    org_id: input.orgId,
    name: input.name.trim(),
    status: input.status ?? "paused",
    script_json: {
      ...DEFAULT_SCRIPT_JSON,
      label,
    },
  };
}
