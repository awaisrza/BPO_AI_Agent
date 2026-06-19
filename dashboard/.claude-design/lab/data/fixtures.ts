export const org = { name: "ABC Call Center", plan: "Starter", botsActive: 8, botsIncluded: 10, pilot: true };
export const stats = { callsToday: 4280, transferRate: 18.4, avgDurationSec: 42, costTodayUsd: 24 };
export const liveCalls = [
  { bot: "Bot-03", campaign: "Medicare AEP", status: "live" as const, duration: "0:38" },
  { bot: "Bot-07", campaign: "Medicare AEP", status: "ringing" as const, duration: "—" },
  { bot: "Bot-01", campaign: "Solar Q1", status: "live" as const, duration: "1:12" },
];
export const navSections = [
  { title: "Operations", items: ["Overview", "Calls", "Leads", "Analytics"] },
  { title: "Management", items: ["Campaigns", "Agents"] },
  { title: "Configuration", items: ["Integrations", "Settings", "Billing"] },
];
