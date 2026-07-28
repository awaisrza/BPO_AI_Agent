# ViciDial integrated flow

When a BPO connects ViciDial and runs a campaign, data flows like this:

## 1. Integrations (once per org)

Dashboard → **Integrations** → save:

- ViciDial server URL / IP
- API user + password

Stored in `organizations.vicidial_*`.

## 2. Campaign mapping

Dashboard → **Campaign editor**:

- **ViciDial campaign ID** — must match hopper campaign in their dialer (e.g. `MEDICARE01`)
- Script, knowledge base, closer for warm transfer
- **Save**

## 3. Bot mapping

Dashboard → **Bots**:

- Each bot gets a **ViciDial agent login** (e.g. `6666`, `agent8001`)
- Must match agent users configured on their ViciDial for AI lines

## 4. GPU supervisor (24/7 on your server)

```bash
cd agent
python run_supervisor.py
```

Polls Supabase every ~20s for `campaigns.status = running` and starts one `fleet_worker` per bot (up to `FLEET_MAX_WORKERS`).

Workers:

- Load script + org ViciDial creds from Supabase
- Pre-warm Chatterbox + Whisper
- Heartbeat `bots.status = idle`

## 5. Run campaign

Dashboard → **Run campaign**:

- Validates Integrations + ViciDial campaign ID + bot agent logins
- Sets campaign + bots to running/idle in Supabase
- If `GPU_SUPERVISOR_URL` is set on the dashboard, POSTs `/sync` so workers start immediately (otherwise supervisor poll ~20s)
- Supervisor picks up and starts workers

## 6. Dialing (BPO side)

- Leads stay in **ViciDial hopper**
- ViciDial dials using mapped **ViciDial campaign ID**
- Live answers bridge to **ViciDial agent user** per bot
- Audio path: SIP/AGI bridge (configure on dialer — see agent README)

## 7. On call

- Agent uses org ViciDial creds from Supabase
- Transfer/disposition via `agent_user` = bot's `vicidial_agent_user`
- Warm transfer to closer selected in campaign editor

## Env (GPU)

```env
NEXT_PUBLIC_SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
VOICE_BACKEND=chatterbox
FLEET_MAX_WORKERS=3
SUPERVISOR_PORT=8770
GPU_SUPERVISOR_SECRET=optional-shared-secret
```

Dashboard (optional — instant worker sync on Run):

```env
GPU_SUPERVISOR_URL=http://YOUR_GPU_IP:8770
GPU_SUPERVISOR_SECRET=optional-shared-secret
```

Optional fallback if org creds not in Supabase:

```env
VICIDIAL_BASE_URL=
VICIDIAL_API_USER=
VICIDIAL_API_PASS=
```
