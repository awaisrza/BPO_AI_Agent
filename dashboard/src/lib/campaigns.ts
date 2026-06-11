import { campaigns as mockCampaigns } from "@/lib/mock-data";

export type Campaign = (typeof mockCampaigns)[number];

const STORAGE_KEY = "ai-fronter-campaigns";

export function slugify(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

export function getStoredCampaigns(): Campaign[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Campaign[]) : [];
  } catch {
    return [];
  }
}

export function saveCampaign(campaign: Campaign): void {
  const existing = getStoredCampaigns();
  const index = existing.findIndex((c) => c.id === campaign.id);
  if (index >= 0) existing[index] = campaign;
  else existing.push(campaign);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(existing));
  window.dispatchEvent(new Event("campaigns-updated"));
}

export function getAllCampaigns(): Campaign[] {
  const mockIds = new Set(mockCampaigns.map((c) => c.id));
  const stored = getStoredCampaigns().filter((c) => !mockIds.has(c.id));
  return [...mockCampaigns, ...stored];
}

export function getCampaignById(id: string): Campaign | undefined {
  return getAllCampaigns().find((c) => c.id === id);
}

export function createCampaign(input: {
  name: string;
  script?: string;
  status?: Campaign["status"];
}): Campaign {
  const id = slugify(input.name);
  if (!id) throw new Error("Campaign name must contain letters or numbers.");

  const existing = getAllCampaigns().find((c) => c.id === id);
  if (existing) throw new Error("A campaign with this name already exists.");

  const campaign: Campaign = {
    id,
    name: input.name.trim(),
    script: input.script?.trim() || `${input.name.trim()} v1`,
    bots: 0,
    status: input.status ?? "paused",
    dials: 0,
    connectRate: 0,
    transferRate: 0,
  };

  saveCampaign(campaign);
  return campaign;
}
