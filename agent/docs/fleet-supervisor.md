# GPU fleet auto-start

When a customer clicks **Run campaign** or **Test dial** in the dashboard, the platform:

1. Sets the campaign (and bots) to running in Supabase
2. Resumes the GPU host if configured (**Vast.ai** or RunPod)
3. Waits for the fleet supervisor / worker health
4. Starts one worker per assigned bot (up to `FLEET_MAX_WORKERS`)

When they click **Pause campaign**, workers for that campaign stop. Optionally the host stops too.

The dashboard can only talk to the GPU over HTTP. If `run_supervisor.py` is not listening, `/sync` cannot create it — the instance **onstart** script must launch the supervisor on every boot.

---

## One-time setup — Vast.ai (recommended for this project)

### 1. Port maps (Connect → Open Ports)

| Public (example) | Internal | Purpose |
|------------------|----------|----------|---------|
| **53604** | **8770** | Fleet supervisor (`/health`, `/sync`) — must map to **8770**, not 53604 |
| **53512** | **10200** | Fleet worker media + `/health` |

### 2. Onstart / launch script (required)

In the Vast instance template or **Edit → Onstart**, set:

```bash
cd /workspace/BPO_AI_Agent/agent && source .venv/bin/activate && \
  bash scripts/restart_fleet_supervisor.sh >> /tmp/supervisor-boot.log 2>&1
```

Without this, starting the instance from the dashboard still leaves the supervisor dead.

On the GPU `agent/.env.local`:

```env
GPU_SUPERVISOR_SECRET=same-secret-as-dashboard
SUPERVISOR_PORT=8770
FLEET_MEDIA_BASE_PORT=10200
FLEET_MAX_WORKERS=3
```

### 3. Dashboard env

```env
GPU_SUPERVISOR_URL=http://YOUR_VAST_PUBLIC_IP:53604
GPU_SUPERVISOR_SECRET=same-secret-as-dashboard
GPU_WORKER_HEALTH_URL=http://YOUR_VAST_PUBLIC_IP:53512/health
VAST_API_KEY=your-vast-api-key
VAST_INSTANCE_ID=46827674
# Optional: stop the Vast instance when the last campaign pauses
# GPU_STOP_POD_ON_IDLE=true
```

Get `VAST_API_KEY` from [Vast → Manage Keys](https://cloud.vast.ai/manage-keys/). `VAST_INSTANCE_ID` is the instance id in Connect (e.g. `46827674`).

Dynamic public IPs: after a stop/start, update `GPU_SUPERVISOR_URL` / `GPU_WORKER_HEALTH_URL` if Vast assigns a new IP.

Restart `npm run dev` after changing env.

---

## One-time setup — RunPod (alternate)

### 1. On the RunPod pod

After the usual Chatterbox install (`agent/docs/chatterbox-gpu-setup.md`), add to `agent/.env.local`:

```env
GPU_SUPERVISOR_SECRET=same-secret-as-dashboard
FLEET_MAX_WORKERS=3
```

Expose port **8770** in RunPod → Connect → HTTP services (note the proxy URL).

### 2. Dashboard env

```env
GPU_SUPERVISOR_URL=https://YOUR_POD_ID-8770.proxy.runpod.net
GPU_SUPERVISOR_SECRET=same-secret-as-dashboard
RUNPOD_API_KEY=your-runpod-api-key
RUNPOD_POD_ID=your-pod-id
GPU_STOP_POD_ON_IDLE=true
```

### 3. RunPod start command

```bash
cd /workspace/ai-fronter/agent && source .venv/bin/activate && python run_supervisor.py
```

---

## Customer flow (after setup)

1. Customer creates campaign + assigns agents
2. Customer clicks **Run campaign** or **Test dial**
3. If the worker is offline, dashboard starts the Vast (or RunPod) instance → onstart launches supervisor → `/sync` spawns workers
4. Bot status / warmup shows **ready**
5. Customer clicks **Pause** → workers stop → host may stop if `GPU_STOP_POD_ON_IDLE=true`

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "GPU auto-start is not configured" | Set `GPU_SUPERVISOR_URL` in dashboard `.env.local` |
| Supervisor timeout after Vast start | Set instance **onstart** to `restart_fleet_supervisor.sh`; map public port → **8770** |
| Worker health timeout / wrong IP | Update `GPU_WORKER_HEALTH_URL` from Vast Connect (dynamic IP) |
| 401 from supervisor | `GPU_SUPERVISOR_SECRET` mismatch between dashboard and pod |
| Workers = 0 | Assign at least one bot to the campaign before Run |
| CUDA OOM | Lower `FLEET_MAX_WORKERS` to 1–2 on L4 |

---

## API

`POST /api/campaigns/{id}/orchestrate` with body `{ "action": "start" | "stop" }` — called automatically by the Run campaign button.

Supervisor endpoints on the GPU pod:

- `GET /health` — liveness
- `POST /sync?campaign_id=UUID` — start workers for running campaign
- `POST /stop?campaign_id=UUID` — stop workers for campaign
