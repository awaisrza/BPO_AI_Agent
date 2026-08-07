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
  vicidial_agent_user: string | null;
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
    topic: "How did you get my number",
    triggers: [
      "how did you get my number",
      "where did you get my number",
      "how'd you get my number",
      "where'd you get my number",
      "how did you get this number",
    ],
    answer:
      "Your number came from a public Medicare outreach list. I can remove you if you'd like — it's just a thirty-second check first.",
  },
  {
    topic: "Already have benefits",
    triggers: [
      "already have all the benefits",
      "already have benefits",
      "have all the benefits i need",
      "don't need anything else",
      "happy with my plan",
      "already covered",
      "i have everything i need",
    ],
    answer:
      "That's great — a lot of folks still qualify for extra savings they didn't know about. Worth a quick thirty-second check?",
  },
  {
    topic: "Who are you with",
    triggers: [
      "who are you with",
      "what company",
      "who do you work for",
      "what agency",
      "who is your company",
      "what's your company",
    ],
    answer:
      "I'm Alex with ABC Benefits — a licensed Medicare benefits group. I'll keep this quick.",
  },
  {
    topic: "Who is calling",
    triggers: ["who is this", "who are you", "who's calling", "what company are you"],
    answer: "This is Alex from ABC Benefits on a recorded line — I'll be quick.",
  },
  {
    topic: "Don't need benefits",
    triggers: [
      "don't need no benefits",
      "don't need benefits",
      "don't want benefits",
      "i don't need that",
      "no benefits",
    ],
    answer:
      "I hear you — this is just a free eligibility review. No cost and no obligation. Takes about thirty seconds.",
  },
  {
    topic: "Not interested",
    triggers: ["not interested", "no thanks", "not for me", "i'm good", "leave me alone"],
    answer:
      "I totally get that — it's just a quick Medicare eligibility check. Takes about thirty seconds, fair enough?",
  },
  {
    topic: "Do not call again",
    triggers: [
      "don't call me again",
      "stop calling",
      "take me off your list",
      "remove my number",
      "do not call",
      "never call again",
      "put me on do not call",
    ],
    answer:
      "I'm sorry about that — I can note that for you. Before I update it, it's just a thirty-second eligibility check — fair enough?",
  },
  {
    topic: "Is this a scam",
    triggers: ["scam", "spam", "legitimate", "real company", "fraud", "is this real"],
    answer:
      "This is a legitimate call from a licensed Medicare benefits group. It may be recorded for quality assurance.",
  },
  {
    topic: "How much does it cost",
    triggers: ["how much", "cost", "price", "is it free", "what's the catch"],
    answer: "The review is free. A licensed specialist can go over exact numbers if you qualify.",
  },
  {
    topic: "Call me back later",
    triggers: ["call me back", "not a good time", "busy right now", "call later", "i'm busy"],
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
