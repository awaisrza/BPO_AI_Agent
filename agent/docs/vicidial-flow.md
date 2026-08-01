# ViciDial production flow

When a BPO configures Integrations, maps campaigns/bots, and clicks **Run campaign**:

## 1. Dashboard → Supabase

- Integrations saves `organizations.vicidial_*`
- Campaign saves `vicidial_campaign_id` + script + closer
- Bots save `vicidial_agent_user`
- **Run** → `POST /api/campaigns/{id}/run` → status `running` + GPU `/sync`

## 2. GPU supervisor (24/7)

```bash
cd agent
python run_supervisor.py
```

- Polls Supabase for running campaigns
- Spawns `python -m app.fleet_worker {bot_id}` per bot (max `FLEET_MAX_WORKERS`)
- Each worker gets media port `8800`, `8801`, `8802`, …

## 3. Fleet worker (per bot)

1. Loads script + org ViciDial creds from Supabase
2. Pre-warms Chatterbox + Whisper
3. Calls ViciDial API: `change_campaign` + `resume_agent` for `vicidial_agent_user`
4. Listens on `ws://GPU_IP:{port}/ws` for live audio
5. Heartbeats `bots.status = idle` (→ `live` on call)

## 4. ViciDial dials (BPO dialer)

- Leads stay in **ViciDial hopper** for `vicidial_campaign_id`
- BPO must have campaign **ACTIVE** in ViciDial
- Auto-dialer feeds answered calls to the AI agent seat

## 5. Audio bridge (BPO IT — one-time)

Install `scripts/vicidial/agi_bridge.py` on the ViciDial/Asterisk server:

```bash
cd agent/scripts/vicidial
sudo bash install_on_dialer.sh
sudo nano /etc/ai-fronter/agent_port_map.json
# Add EAGI lines from extensions_ai_fronter.conf.example → dialplan reload
```

Full steps: `scripts/vicidial/README.md`.

Worker ports are listed in supervisor status:

```bash
curl http://GPU_IP:8770/status
```

The bridge resolves `vicidial_agent_user` → `media_port` via config or live `/status`.

## 6. On call

- Pipeline runs with `mic_test=False`
- Qualifies lead via FSM
- **Transfer:** `warm_transfer(agent_user, closer_user=transfer_closer_user)` + disposition `XFER`
- **Not interested:** disposition `NI` + hangup

## Env (GPU)

```env
NEXT_PUBLIC_SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
VOICE_BACKEND=chatterbox
FLEET_MAX_WORKERS=3
FLEET_MEDIA_BASE_PORT=8800
SUPERVISOR_PORT=8770
VICIDIAL_BASE_URL=          # fallback if org creds missing
VICIDIAL_API_USER=
VICIDIAL_API_PASS=
```

## Env (dashboard)

```env
GPU_SUPERVISOR_URL=http://YOUR_GPU_IP:8770
GPU_SUPERVISOR_SECRET=      # optional, match GPU
```
