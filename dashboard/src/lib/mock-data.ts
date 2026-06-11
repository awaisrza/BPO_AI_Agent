export const org = {
  name: "ABC Call Center",
  plan: "Starter",
  botsIncluded: 10,
  botsActive: 8,
  minutesIncluded: 35000,
  minutesUsed: 24200,
  pilot: true,
};

export const stats = {
  callsToday: 4280,
  transferRate: 18.4,
  avgDurationSec: 42,
  costTodayUsd: 24,
  connectRate: 34,
  costPerTransfer: 18,
  humanCostPerTransfer: 95,
  activeMinPerBot: 3420,
};

export const liveCalls = [
  { bot: "Bot-03", campaign: "Medicare AEP", status: "live" as const, duration: "0:38" },
  { bot: "Bot-07", campaign: "Medicare AEP", status: "ringing" as const, duration: "—" },
  { bot: "Bot-01", campaign: "Solar Q1", status: "live" as const, duration: "1:12" },
  { bot: "Bot-05", campaign: "Medicare AEP", status: "dialing" as const, duration: "—" },
];

export const bots = [
  { id: "Bot-01", campaign: "Solar Q1", status: "live", callsPerHour: 142, activeNow: "1:12" },
  { id: "Bot-02", campaign: "Medicare AEP", status: "dialing", callsPerHour: 138, activeNow: "—" },
  { id: "Bot-03", campaign: "Medicare AEP", status: "live", callsPerHour: 145, activeNow: "0:38" },
  { id: "Bot-04", campaign: "Medicare AEP", status: "idle", callsPerHour: 0, activeNow: "—" },
  { id: "Bot-05", campaign: "Medicare AEP", status: "dialing", callsPerHour: 131, activeNow: "—" },
  { id: "Bot-06", campaign: "Medicare AEP", status: "live", callsPerHour: 140, activeNow: "0:55" },
  { id: "Bot-07", campaign: "Medicare AEP", status: "ringing", callsPerHour: 136, activeNow: "—" },
  { id: "Bot-08", campaign: "Medicare AEP", status: "live", callsPerHour: 148, activeNow: "2:01" },
];

export const campaigns = [
  {
    id: "med-aep",
    name: "Medicare AEP",
    script: "Medicare AEP v2",
    bots: 8,
    status: "running" as const,
    dials: 12400,
    connectRate: 34,
    transferRate: 19,
  },
  {
    id: "solar-q1",
    name: "Solar Q1",
    script: "Solar intro",
    bots: 2,
    status: "running" as const,
    dials: 3200,
    connectRate: 31,
    transferRate: 16,
  },
  {
    id: "debt-rem",
    name: "Debt Reminder",
    script: "Debt v1",
    bots: 0,
    status: "paused" as const,
    dials: 0,
    connectRate: 0,
    transferRate: 0,
  },
];

export const leads = [
  { phone: "+1 (555) 201-4521", name: "John M.", status: "transferred", campaign: "Medicare AEP", lastAttempt: "10:42 AM", outcome: "Qualified" },
  { phone: "+1 (555) 883-2290", name: "Sarah K.", status: "qualified", campaign: "Medicare AEP", lastAttempt: "10:40 AM", outcome: "Interested" },
  { phone: "+1 (555) 442-1188", name: "—", status: "voicemail", campaign: "Medicare AEP", lastAttempt: "10:39 AM", outcome: "AMD" },
  { phone: "+1 (555) 331-9022", name: "Mike R.", status: "not_interested", campaign: "Solar Q1", lastAttempt: "10:35 AM", outcome: "Declined" },
  { phone: "+1 (555) 774-3301", name: "Lisa P.", status: "dialed", campaign: "Medicare AEP", lastAttempt: "10:33 AM", outcome: "No answer" },
  { phone: "+1 (555) 612-8844", name: "—", status: "new", campaign: "Medicare AEP", lastAttempt: "—", outcome: "—" },
];

export const leadSummary = {
  total: 12400,
  dialed: 8920,
  qualified: 1640,
  transferred: 412,
  dnc: 89,
};

export const calls = [
  {
    id: "1",
    time: "10:42 AM",
    campaign: "Medicare AEP",
    phone: "+1 (555) 201-4521",
    duration: "38s",
    outcome: "Qualified",
    transferred: true,
    transcript: [
      { role: "bot", text: "Hi, this is Sarah calling about your Medicare benefits review." },
      { role: "caller", text: "Yes, I'm listening." },
      { role: "bot", text: "Are you 65 or older and currently on Medicare Part A?" },
      { role: "caller", text: "Yes I am." },
      { role: "bot", text: "Great — I'll connect you with a licensed specialist now." },
    ],
    disposition: "XFER",
    queue: "closers-01",
    sentiment: "Interested",
  },
  {
    id: "2",
    time: "10:41 AM",
    campaign: "Medicare AEP",
    phone: "+1 (555) 883-2290",
    duration: "12s",
    outcome: "Voicemail",
    transferred: false,
    transcript: [],
    disposition: "AM",
    queue: "—",
    sentiment: "—",
  },
  {
    id: "3",
    time: "10:38 AM",
    campaign: "Solar Q1",
    phone: "+1 (555) 331-9022",
    duration: "55s",
    outcome: "Not interested",
    transferred: false,
    transcript: [
      { role: "bot", text: "Hi, I'm calling about solar savings programs in your area." },
      { role: "caller", text: "Not interested, please remove me." },
    ],
    disposition: "NI",
    queue: "—",
    sentiment: "Negative",
  },
];

export const funnel = [
  { label: "Dials", value: 12400 },
  { label: "Connect", value: 4216 },
  { label: "Qualify", value: 1640 },
  { label: "Transfer", value: 412 },
];

export const transferTrend = [
  { day: "Mon", rate: 16.2 },
  { day: "Tue", rate: 17.8 },
  { day: "Wed", rate: 18.1 },
  { day: "Thu", rate: 19.4 },
  { day: "Fri", rate: 18.4 },
  { day: "Sat", rate: 17.2 },
  { day: "Sun", rate: 0 },
];

export const users = [
  { name: "Admin User", email: "admin@abccall.com", role: "Admin" },
  { name: "Campaign Mgr", email: "ops@abccall.com", role: "Campaign Manager" },
  { name: "Supervisor", email: "sup@abccall.com", role: "Supervisor" },
];
