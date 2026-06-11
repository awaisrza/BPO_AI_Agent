export type CampaignStatus = "running" | "paused";

export type ScriptJson = {
  label?: string;
  greeting: string;
  pitch: string;
  qualifying_questions: string[];
  transfer_line: string;
  not_interested_line: string;
  transfer_preset: string;
};

export type CampaignRow = {
  id: string;
  org_id: string;
  name: string;
  status: CampaignStatus;
  script_json: ScriptJson;
  voice_id: string | null;
  vicidial_campaign_id: string | null;
  dials: number;
  connect_rate: number;
  transfer_rate: number;
  created_at: string;
  updated_at: string;
};

export type BotStatus = "live" | "idle" | "dialing" | "ringing" | "offline";

export type BotRow = {
  id: string;
  org_id: string;
  campaign_id: string | null;
  name: string;
  status: BotStatus;
  created_at: string;
  campaigns?: { name: string } | null;
};

export type ProfileRow = {
  id: string;
  org_id: string;
  email: string;
  name: string | null;
  role: string;
};

export type OrganizationRow = {
  id: string;
  name: string;
  plan: string;
  vicidial_url: string | null;
  vicidial_user: string | null;
  vicidial_pass: string | null;
  transfer_preset: string | null;
  bots_included: number;
  minutes_included: number;
};

export const DEFAULT_SCRIPT_JSON: ScriptJson = {
  greeting: "Hi, this is Alex calling on a recorded line. How are you today?",
  pitch:
    "Great — I will be quick. We help homeowners cut their electricity bill with no upfront cost. Do you currently own your home?",
  qualifying_questions: [
    "Do you own your home?",
    "Is your average monthly electric bill over 100 dollars?",
  ],
  transfer_line: "Perfect — let me connect you with a specialist right now, one moment.",
  not_interested_line: "No problem at all, thanks for your time. Have a great day!",
  transfer_preset: "closers-01",
};
