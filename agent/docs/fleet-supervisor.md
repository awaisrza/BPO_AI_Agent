# GPU fleet auto-start

When a customer clicks **Run campaign** in the dashboard, the platform:

1. Sets the campaign (and bots) to running in Supabase
2. Resumes the RunPod GPU pod (if configured)
3. Waits for the fleet supervisor to respond
4. Starts one worker per assigned bot (up to `FLEET_MAX_WORKERS`)

When they click **Pause campaign**, workers for that campaign stop. Optionally the RunPod pod stops too.

---

## One-time setup

### 1. On the RunPod pod

After the usual Chatterbox install (`agent/docs/chatterbox-gpu-setup.md`), add to `agent/.env.local`:

```env
GPU_SUPERVISOR_SECRET=same-secret-as-dashboard
FLEET_MAX_WORKERS=3
```

Start the supervisor (keep it running — use `tmux`, systemd, or RunPod start command):

```bash
cd ai-fronter/agent
source .venv/bin/activate
python run_supervisor.py
```

Expose port **8770** in RunPod → Connect → HTTP services (note the proxy URL).

### 2. On the dashboard server

Add to `dashboard/.env.local`:

```env
GPU_SUPERVISOR_URL=https://YOUR_POD_ID-8770.proxy.runpod.net
GPU_SUPERVISOR_SECRET=same-secret-as-dashboard
RUNPOD_API_KEY=your-runpod-api-key
RUNPOD_POD_ID=your-pod-id
GPU_STOP_POD_ON_IDLE=true
```

Restart `npm run dev` (or redeploy).

### 3. RunPod start command (optional)

Set the pod template **Docker start command** or SSH startup script to:

```bash
cd /workspace/ai-fronter/agent && source .venv/bin/activate && python run_supervisor.py
```

Then the supervisor is always listening when the pod is up.

---

## Customer flow (after setup)

1. Customer creates campaign + assigns agents
2. Customer clicks **Run campaign**
3. Dashboard resumes RunPod → supervisor syncs → GPU workers start
4. Bot status in dashboard shows **Ready** (heartbeat from workers)
5. Customer clicks **Pause** → workers stop → pod may stop if `GPU_STOP_POD_ON_IDLE=true`

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "GPU auto-start is not configured" | Set `GPU_SUPERVISOR_URL` in dashboard `.env.local` |
| Supervisor timeout | Pod not running, port 8770 not exposed, or supervisor not started |
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
