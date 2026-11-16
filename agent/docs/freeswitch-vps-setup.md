# FreeSWITCH SIP edge VPS setup

Step-by-step guide to stand up **production telephony ingress** on a small VPS. FreeSWITCH terminates SIP from ViciDial remote agents; **`mod_audio_stream`** streams audio to the existing Python SIP edge (`run_sip_edge.py`), which bridges to GPU `fleet_worker` `/ws`.

**Time:** ~45–60 minutes on a fresh Ubuntu 22.04/24.04 VPS.

See also: [sip-edge-setup.md](./sip-edge-setup.md) · [bpo-sip-onboarding.md](./bpo-sip-onboarding.md)

---

## Architecture (this VPS)

```
ViciDial remote agent  sip:6666@acme.bots.yourplatform.com
        │ UDP 5060 + RTP 10000–20000
        ▼
FreeSWITCH (mod_sofia + mod_audio_stream)
        │ ws://127.0.0.1:8790/v1/stream/fs
        ▼
run_sip_edge.py  (systemd: ai-fronter-sip-edge)
        │ Redis resolve {org_id}:{agent_user}
        │ ws://GPU:8800/ws  (Telnyx JSON / PCMU)
        ▼
fleet_worker → inference_pool → vicidial_session (unchanged)
```

**Lab path (`agi_bridge.py` on BPO box) is deprecated for production.**

---

## 1. VPS checklist

| Item | Recommendation |
|------|----------------|
| **Size** | 2 vCPU, 4 GB RAM (~10 concurrent bot lines pilot) |
| **OS** | Ubuntu 22.04 or 24.04 LTS (Debian 12 also works) |
| **Provider** | Any (Hetzner, DigitalOcean, Vultr, etc.) ~$20/mo |
| **Co-location** | FreeSWITCH + `run_sip_edge.py` on **same host** for pilot |

### Firewall (UFW example)

Restrict to BPO dialer IP when known:

```bash
# Replace 198.51.100.0/24 with BPO outbound SIP IP(s)
ufw allow from 198.51.100.0/24 to any port 5060 proto udp
ufw allow from 198.51.100.0/24 to any port 10000:20000 proto udp
ufw allow OpenSSH
ufw enable
```

| Port | Protocol | Purpose |
|------|----------|---------|
| 5060 | UDP | SIP signaling |
| 10000–20000 | UDP | RTP media |
| 8790 | TCP | SIP edge HTTP/WS (**localhost only** in pilot) |
| 22 | TCP | SSH admin |

### DNS

Point wildcard to VPS public IP:

| Type | Name | Value |
|------|------|-------|
| A | `bots.yourplatform.com` | `203.0.113.10` |
| A | `*.bots.yourplatform.com` | `203.0.113.10` |

BPO SIP URI examples:

- Slug: `sip:6666@acme-corp.bots.yourplatform.com`
- UUID: `sip:6666@550e8400-e29b-41d4-a716-446655440000.bots.yourplatform.com`

---

## 2. Clone repo & Python SIP edge

```bash
sudo useradd -r -m -d /opt/ai-fronter -s /bin/bash ai-fronter || true
sudo mkdir -p /opt/ai-fronter /etc/ai-fronter
sudo chown ai-fronter:ai-fronter /opt/ai-fronter

sudo -u ai-fronter git clone https://github.com/YOUR_ORG/ai-fronter.git /opt/ai-fronter
cd /opt/ai-fronter/agent
sudo -u ai-fronter python3 -m venv .venv
sudo -u ai-fronter .venv/bin/pip install -r requirements.txt
```

### Environment file

```bash
sudo cp deploy/sip-edge/ai-fronter-sip-edge.env.example /etc/ai-fronter/sip-edge.env
sudo chmod 600 /etc/ai-fronter/sip-edge.env
sudo nano /etc/ai-fronter/sip-edge.env
```

Required variables:

```env
SIP_EDGE_DOMAIN=bots.yourplatform.com
SIP_EDGE_PUBLIC_IP=<VPS_PUBLIC_IP>
SIP_EDGE_HTTP_PORT=8790
REDIS_URL=redis://<redis-host>:6379/0
GPU_SUPERVISOR_URL=http://<GPU_PUBLIC_IP>:8770
GPU_SUPERVISOR_SECRET=<secret>
SIP_ORG_SLUG_MAP=acme-corp=<org-uuid>
NEXT_PUBLIC_SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<key>
```

### systemd

```bash
sudo cp deploy/sip-edge/ai-fronter-sip-edge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ai-fronter-sip-edge
sudo systemctl start ai-fronter-sip-edge
sudo systemctl status ai-fronter-sip-edge
```

---

## 3. Install FreeSWITCH + mod_audio_stream

We use **[mod_audio_stream](https://github.com/amigniter/mod_audio_stream)** (not the legacy `mod_audio_fork`). Pilot uses the **community build**; commercial v1.0.3+ adds `STREAM_PLAYBACK` for simpler bidirectional audio.

```bash
cd /opt/ai-fronter/agent
export SIP_EDGE_DOMAIN=bots.yourplatform.com
export SIP_EDGE_PUBLIC_IP=<VPS_PUBLIC_IP>
sudo bash scripts/sip/install-freeswitch.sh
```

Manual verify:

```bash
fs_cli -x "module_exists mod_audio_stream"
# +OK true

fs_cli -x "reloadxml"
```

### Sofia external profile (PCMU)

Ensure `/etc/freeswitch/sip_profiles/external.xml` accepts inbound and advertises your public IP:

```xml
<param name="ext-rtp-ip" value="$${external_rtp_ip}"/>
<param name="ext-sip-ip" value="$${external_sip_ip}"/>
<param name="inbound-codec-prefs" value="PCMU,PCMA"/>
<param name="outbound-codec-prefs" value="PCMU,PCMA"/>
<param name="rtp-start-port" value="10000"/>
<param name="rtp-end-port" value="20000"/>
```

Set in `/etc/freeswitch/vars.xml`:

```xml
<X-PRE-PROCESS cmd="set" data="external_sip_ip=<VPS_PUBLIC_IP>"/>
<X-PRE-PROCESS cmd="set" data="external_rtp_ip=<VPS_PUBLIC_IP>"/>
<X-PRE-PROCESS cmd="set" data="domain=<SIP_EDGE_DOMAIN>"/>
```

Tell FreeSWITCH where SIP edge listens (optional; default `127.0.0.1:8790`):

```bash
# /etc/default/freeswitch or environment drop-in
AI_FRONTER_STREAM_HOST=127.0.0.1:8790
```

Dialplan and Lua ship in:

- `/etc/freeswitch/dialplan/public/ai_fronter.xml`
- `/etc/freeswitch/scripts/ai_fronter_stream.lua`

**WebSocket URL used by FreeSWITCH:**

```
ws://127.0.0.1:8790/v1/stream/fs?agent_user=6666&org_slug=acme-corp&caller=...&callee=6666
```

Use `/v1/stream/fs` (not `/v1/stream`) — FreeSWITCH sends **L16 binary**; the FS adapter converts to **PCMU Telnyx JSON** for the GPU worker.

---

## 4. GPU prerequisites

Before any call test, from the **dashboard**:

1. **Run campaign** — starts `fleet_supervisor`, `inference_pool`, `fleet_worker`
2. Bot has **ViciDial agent user** (e.g. `6666`) matching SIP destination
3. Redis on GPU (or shared) has worker registered with `org_id`

Quick checks from SIP VPS:

```bash
curl -s http://127.0.0.1:8790/health
curl -s "http://127.0.0.1:8790/v1/route?agent_user=6666&org_id=<ORG_UUID>"
curl -s http://<GPU_IP>:8800/health
curl -s http://<GPU_IP>:8780/health
```

---

## 5. Verification

### A. SIP edge → GPU (no FreeSWITCH)

```bash
cd /opt/ai-fronter/agent && source .venv/bin/activate

curl http://127.0.0.1:8790/health
# {"status":"ok","domain":"bots.yourplatform.com"}

curl "http://127.0.0.1:8790/v1/route?agent_user=6666&org_id=<ORG_UUID>"
# {"ok":true,"source":"redis","media_port":8800,...}

python -m app.sip_edge.test_client \
  --agent 6666 \
  --org-id <ORG_UUID> \
  --sip-edge ws://127.0.0.1:8790
```

Expect `.` characters as bot audio returns (or check GPU worker logs for `VICIDIAL WS handler`).

### B. FreeSWITCH → SIP edge

**Loopback test** (on VPS):

```bash
fs_cli -x "originate {origination_caller_id_number=15551234567}loopback/6666/default &park()"
```

Or register a softphone to `6666@<VPS_IP>` with domain `acme-corp.bots.yourplatform.com`.

Watch logs:

```bash
journalctl -u ai-fronter-sip-edge -f
fs_cli
/freeswitch> console loglevel debug
```

Expect:

1. `ai_fronter_stream: ws://127.0.0.1:8790/v1/stream/fs?...`
2. SIP edge: `FreeSWITCH bridge → ws://GPU:8800/ws`
3. GPU worker: pipeline start + greeting

**Hangup:** `uuid_audio_stream` stop runs on channel destroy; SIP edge closes GPU bridge.

### C. ViciDial remote agent (pilot BPO)

1. Dashboard → **Integrations** → copy SIP URI for bot `6666`
2. ViciDial admin → remote agent → external address = that URI
3. Campaign **Run** on dashboard; hopper has test lead
4. Place call → lead hears bot greeting with normal pauses
5. Warm transfer / disposition via existing ViciDial API creds

---

## 6. Operational runbook

| Symptom | Check |
|---------|--------|
| Fast busy / no ring | Firewall UDP 5060; Sofia profile up; BPO IP allowlist |
| Ring but no audio | RTP 10000–20000 open; `external_rtp_ip` in vars.xml; codec PCMU |
| Connect then silence | `/v1/route` returns worker; GPU `/health` `ready=true`; inference pool `/health` |
| WS fails immediately | `systemctl status ai-fronter-sip-edge`; URL uses `/v1/stream/fs` |
| Wrong bot / no worker | Org-scoped SIP URI; Redis `aifronter:tenant:{org_id}:{agent_user}` |
| One-way audio (bot only) | `STREAM_PLAYBACK=true`; mod_audio_stream v1.0.3+ or ESL playback |
| Two orgs same agent `6666` | Must use different `{org_ref}` subdomains + tenant Redis keys |

### Useful commands

```bash
# SIP edge
journalctl -u ai-fronter-sip-edge -f
curl "http://127.0.0.1:8790/v1/route?agent_user=6666&org_id=UUID"

# FreeSWITCH
fs_cli -x "sofia status"
fs_cli -x "show channels"
fs_cli -x "uuid_audio_stream <uuid> stop"

# Redis (shared)
redis-cli KEYS 'aifronter:tenant:*'
```

---

## 7. Pilot vs production summary

| | Pilot (lab) | Production (this doc) |
|---|-------------|------------------------|
| BPO install | `agi_bridge.py` on dialer | **None** |
| Ingress | AudioSocket :9092 | SIP UDP 5060 |
| Media bridge | BPO-side Python | **SIP VPS** FreeSWITCH + SIP edge |
| Multi-tenant | Optional | `{org_id}:{agent_user}` required at scale |

---

## 8. Files in repo

| Path | Purpose |
|------|---------|
| `agent/run_sip_edge.py` | SIP edge entrypoint |
| `agent/app/sip_freeswitch_bridge.py` | FS ↔ GPU adapter |
| `agent/scripts/sip/install-freeswitch.sh` | FS + module installer |
| `agent/scripts/sip/freeswitch/ai_fronter.xml` | Dialplan template |
| `agent/scripts/sip/freeswitch/ai_fronter_stream.lua` | Starts `uuid_audio_stream` |
| `agent/deploy/sip-edge/*.service` | systemd unit + env example |

**Out of scope for pilot:** Kamailio/rtpengine cluster, multi-region SIP — design allows adding later at 100+ bots.
