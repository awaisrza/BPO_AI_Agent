export type CampaignStatus = "running" | "paused";

export type KnowledgeEntry = {
  topic: string;
  triggers: string[];
  answer: string;
};

export type ScriptJson = {
  label?: string;
  greeting: string;
  pitch: string;
  qualifying_questions: string[];
  transfer_line: string;
  not_interested_line: string;
  transfer_preset: string;
  /** ViciDial agent user id for warm transfer (AGENTDIRECT). */
  transfer_closer_user?: string | null;
  transfer_closer_name?: string | null;
  knowledge_base?: KnowledgeEntry[];
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
  bots_included?: number;
  minutes_included?: number;
  settings_json?: Record<string, unknown> | null;
};

export const DEFAULT_KNOWLEDGE_BASE: KnowledgeEntry[] = [
  {
    topic: "Who is calling?",
    triggers: ["who is this", "who are you", "who's calling", "what company"],
    answer: "This is Sarah from ABC Benefits on a recorded line — I'll be quick.",
  },
  {
    topic: "Is this a scam?",
    triggers: ["scam", "spam", "legitimate", "real company", "fraud"],
    answer: "This is a legitimate call. It may be recorded for quality assurance.",
  },
  {
    topic: "How much does it cost?",
    triggers: ["how much", "cost", "price", "free", "catch"],
    answer: "The licensed specialist can go over exact numbers after I connect you.",
  },
  {
    topic: "Call me back later",
    triggers: ["call me back", "not a good time", "busy right now", "later"],
    answer: "Sure — what time works best for you tomorrow?",
  },
];

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
  knowledge_base: DEFAULT_KNOWLEDGE_BASE,
};
