# SIP edge setup (production Phase 1)

Production telephony ingress runs on **your SIP edge VPS**, not on the BPO ViciDial box. BPOs only configure a ViciDial remote agent to point at your SIP URI.

## Architecture

| Layer | Host | Role |
|-------|------|------|
| **SIP edge** | Small VPS (2 vCPU, 4GB) | Accept SIP/RTP from ViciDial; bridge PCMU to GPU worker WebSocket |
| **GPU** | RunPod L4 | `fleet_supervisor`, `inference_pool`, `fleet_worker` (unchanged) |
| **BPO** | Their ViciDial | Remote agent config only — **no install** |

### Pilot vs production

| | Pilot (lab) | Production |
|---|-------------|------------|
| BPO install | `agi_bridge.py` on dialer | None |
| Media path | AudioSocket → bridge → GPU `/ws` | SIP → FreeSWITCH → SIP edge `/v1/stream` → GPU `/ws` |
| Multi-tenant | Single org assumed | `{org_id}:{agent_user}` in Redis |

## Components

- **`run_sip_edge.py`** — HTTP/WS control plane (port **8790** default)
- **`sip_media_bridge.py`** — Relays Telnyx JSON (PCMU @ 8 kHz) to `fleet_worker` `/ws`
- **`sip_edge/router.py`** — Resolves `{org_id, agent_user}` via Redis + supervisor `/route`
- **FreeSWITCH** (recommended) — SIP termination + `mod_audio_stream` to our WebSocket

## VPS requirements (≈10 bots)

- 2 vCPU, 4 GB RAM (~$20/mo)
- UDP **5060** (SIP) + RTP range **10000–20000** open to BPO dialer IP(s)
- TCP **8790** for SIP edge HTTP/WebSocket (internal or VPN to FreeSWITCH)

GPU host stays separate (RunPod L4).

## 1. Deploy SIP edge service

On the SIP VPS (can co-locate with FreeSWITCH for dev):

```bash
cd /opt/ai-fronter/agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env.local   # set REDIS_URL, GPU_SUPERVISOR_URL, SIP_EDGE_DOMAIN
python run_sip_edge.py
```

Health check:

```bash
curl http://127.0.0.1:8790/health
curl "http://127.0.0.1:8790/v1/route?agent_user=6666&org_id=YOUR_ORG_UUID"
```

## 2. FreeSWITCH (recommended)

Full VPS guide: **[freeswitch-vps-setup.md](./freeswitch-vps-setup.md)** (install, dialplan, systemd, verification A→B→C).

We use **FreeSWITCH** with **`mod_audio_stream`**. FreeSWITCH connects to:

```
ws://127.0.0.1:8790/v1/stream/fs?agent_user=6666&org_slug=acme-corp
```

Use **`/v1/stream/fs`** for FreeSWITCH (L16 binary ↔ PCMU adapter). The Telnyx-shaped **`/v1/stream`** endpoint is for `test_client` and soft tests only.

Templates: `agent/scripts/sip/freeswitch/ai_fronter.xml`, `ai_fronter_stream.lua`, `agent/deploy/sip-edge/`.

## 3. Environment

```env
SIP_EDGE_DOMAIN=bots.yourplatform.com
SIP_EDGE_PUBLIC_IP=203.0.113.10
SIP_EDGE_HTTP_PORT=8790
REDIS_URL=redis://GPU_OR_SHARED:6379/0
GPU_SUPERVISOR_URL=http://GPU_PUBLIC_IP:8770
GPU_SUPERVISOR_SECRET=...
SIP_ORG_SLUG_MAP=acme-corp=550e8400-e29b-41d4-a716-446655440000
```

Org slug map is optional if SIP URIs use org UUID subdomains: `sip:6666@550e8400-....bots.yourplatform.com`.

## 4. Test without FreeSWITCH

Simulate the FreeSWITCH WebSocket client:

```bash
# Requires a running fleet_worker on GPU
python -m app.sip_edge.test_client --agent 6666 --org-id YOUR_ORG_UUID \
  --sip-edge ws://127.0.0.1:8790
```

Or connect a softphone to FreeSWITCH and place a call to `6666@your SIP domain`.

## 5. Codec

**PCMU (G.711 μ-law) @ 8 kHz** — same as Telnyx Media Streams and `vicidial_session.py`. Do not change conversation or pipeline code; only transport lands on existing `/ws`.

## Related docs

- [bpo-sip-onboarding.md](./bpo-sip-onboarding.md) — hand to BPO admins
- [fleet-supervisor.md](./fleet-supervisor.md) — GPU worker orchestration
