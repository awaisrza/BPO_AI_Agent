# BPO SIP onboarding (zero server install)

Give this checklist to a BPO admin. They **do not** SSH to their dialer or install `agi_bridge.py`.

## What the BPO configures

1. **ViciDial API user** — entered in your dashboard → Integrations (you store creds for warm transfer/disposition).
2. **Remote agent per bot** — one per AI seat in ViciDial.
3. **Firewall** — allow their dialer → your SIP edge UDP **5060** + RTP **10000–20000**.

## Remote agent settings (ViciDial admin)

| Field | Value |
|-------|--------|
| Agent user | e.g. `6666` (must match bot in dashboard) |
| Campaign | Their campaign (hopper / lists) |
| External extension / remote address | **Your SIP URI** (see dashboard Integrations) |

### SIP URI format

```
sip:{agent_user}@{org_ref}.{your_domain}
```

Examples:

- UUID org: `sip:6666@550e8400-e29b-41d4-a716-446655440000.bots.yourplatform.com`
- Slug org: `sip:6666@acme-corp.bots.yourplatform.com`

Get the exact URI from **Dashboard → Integrations → SIP remote agent**.

## What you configure (platform)

| Step | Where |
|------|--------|
| Run campaign | Dashboard → Campaign → **Run** (starts GPU worker + inference pool) |
| Bot agent user | Dashboard → Bots → ViciDial user `6666` |
| Redis + supervisor | GPU host env (`REDIS_URL`, `GPU_SUPERVISOR_URL`) |
| SIP edge | VPS: `python run_sip_edge.py` + FreeSWITCH — see [freeswitch-vps-setup.md](./freeswitch-vps-setup.md) |

## Test call flow

1. Clear hopper / use a test lead.
2. Start campaign from dashboard (worker shows **idle** on `/health`).
3. BPO places or auto-dials a lead; remote agent connects to your SIP URI.
4. Lead answers → bot greeting (same script/pauses as lab bridge path).
5. Warm transfer / hangup → existing ViciDial API dispositions.

## Troubleshooting

| Symptom | Check |
|---------|--------|
| WS fails | `run_sip_edge` running; FreeSWITCH uses `/v1/stream/fs` (not `/v1/stream`) |
| Wrong bot / no worker | `GET /v1/route?org_id=&agent_user=` on SIP edge; Redis `aifronter:tenant:*` |
| Bot silent after connect | GPU worker `/health` `ready=true`; inference pool `/health` |
| Two BPOs both use agent `6666` | Must use **org-scoped** SIP URI + Redis tenant keys |

## Lab fallback (internal only)

Single-BPO pilots may still use `agent/scripts/vicidial/agi_bridge.py` on the dialer box. **Not for production multi-BPO rollout.**

## Time estimate

A BPO admin with ViciDial remote-agent access can complete steps 1–3 in **under 15 minutes** with no SSH from your team.
