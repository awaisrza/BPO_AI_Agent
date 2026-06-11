# AI Fronter Dashboard

Professional BPO dashboard for managing AI fronter bots, campaigns, calls, and pilot analytics.

## Run locally

```bash
cd dashboard
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Pages

| Route | Purpose |
|-------|---------|
| `/` | Overview — live calls, KPIs, transfer trend |
| `/campaigns` | Campaign list |
| `/campaigns/[id]` | Script editor — opening, qualify, transfer rules |
| `/bots` | Bot fleet — concurrent lines |
| `/leads` | Lead outcomes synced from ViciDial |
| `/calls` | Call log + transcript detail |
| `/analytics` | Pilot report — funnel, cost comparison |
| `/integrations` | ViciDial + RunPod GPU setup |
| `/settings` | Org, users, compliance |
| `/billing` | Usage + invoice (free pilot) |

All data is **mock** for now — wire to Supabase + agent API next.

## Stack

- Next.js 15 (App Router)
- TypeScript
- Tailwind CSS
- Lucide icons
