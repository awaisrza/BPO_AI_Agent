# ai-fronter

AI **fronter** bots for call centers / BPOs. A bot dials leads (via the BPO's ViciDial dialer),
runs the script, qualifies the prospect, and **warm-transfers interested leads to a human closer**.

It replaces the high-churn fronter/dialer seat while keeping the BPO's closers — sold per concurrent
bot/month.

## Monorepo layout

```
ai-fronter/
├── agent/        # Python · Pipecat voice pipeline (STT → LLM → TTS) + ViciDial integration
└── dashboard/    # Next.js · Supabase · Stripe — campaigns, scripts, call logs, per-bot billing
```

## Stack

| Layer            | Pilot (managed)          | Production (cost-optimized)              |
| ---------------- | ------------------------ | --------------------------------------- |
| Dialer/telephony | BPO's ViciDial (AGI/API) | same                                    |
| Orchestration    | Pipecat (self-hosted)    | same                                    |
| STT              | Deepgram Nova-3          | self-hosted faster-whisper              |
| LLM              | Gemini 2.5 Flash-Lite    | Gemini 2.5 Flash-Lite (keep managed)    |
| TTS              | Fish Audio               | self-hosted Piper/Kokoro + cached audio |
| Dashboard        | Next.js + Supabase       | same                                    |
| Billing          | Invoice + bank/Wise (Safepay later) | same                          |

See [`docs/architecture.md`](docs/architecture.md) for the full design and unit economics.

## Quick start

```bash
# 1. Agent (Python 3.11+)
cd agent
python -m venv .venv
# Windows PowerShell (if activate is blocked, use this instead):
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m app.main
cp .env.example .env                                 # fill in API keys

# 2. Dashboard (Node 20+)
cd dashboard
npm install
cp .env.example .env.local                           # fill in Supabase + Stripe keys
npm run dev
```

## Status

Scaffold / pre-pilot. The goal of the pilot is to measure **active minutes per bot** and the
**transfer rate** on one real campaign — those numbers drive pricing. Do not self-host STT/TTS until
the pilot proves volume.
