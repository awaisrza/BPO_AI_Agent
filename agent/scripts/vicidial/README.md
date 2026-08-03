# ViciDial audio bridge (BPO dialer side)

Each GPU **fleet worker** exposes a WebSocket at:

```
ws://GPU_PUBLIC_IP:{media_port}/ws
```

Ports: `8800`, `8801`, `8802` (one per bot — see `curl http://GPU_IP:8770/status`).

## Protocol

Uses **Telnyx Media Streams** JSON format (PCMU @ 8 kHz) — same as your Telnyx phone test. The GPU agent already speaks this protocol.

## Quick install (BPO Asterisk server)

```bash
# 1. Copy bridge + config
sudo mkdir -p /etc/ai-fronter /usr/local/bin
sudo cp agi_bridge.py /usr/local/bin/ai-fronter-bridge.py
sudo chmod +x /usr/local/bin/ai-fronter-bridge.py
sudo cp agent_port_map.json.example /etc/ai-fronter/agent_port_map.json
sudo nano /etc/ai-fronter/agent_port_map.json   # set gpu_host + agent → port map

# 2. Python dependency (dialer server)
sudo pip3 install websocket-client

# 3. Test GPU reachability (no Asterisk needed)
/usr/local/bin/ai-fronter-bridge.py --test-ws 6666
```

## AGI bridge script

`agi_bridge.py` is an **EAGI** script that:

1. Reads the ViciDial agent login (dialplan argument, e.g. `6666`)
2. Resolves the GPU worker port (config file, env, or live `/status`)
3. Opens WebSocket to `ws://GPU_HOST:{port}/ws`
4. Sends Telnyx `start` handshake
5. Forwards caller audio EAGI fd 3 ↔ GPU (PCMU base64 `media` events)

Install path used in examples:

```
/usr/local/bin/ai-fronter-bridge.py
```

### Port resolution (first match wins)

| Priority | Source |
|----------|--------|
| 1 | `AI_FRONTER_MEDIA_PORT` env var |
| 2 | `/etc/ai-fronter/agent_port_map.json` → `agents["6666"]` |
| 3 | `GET http://GPU:8770/status` → match `vicidial_agent_user` |

Copy `agent_port_map.json.example` and edit `gpu_host` + `agents` map. Or rely on live supervisor lookup after dashboard **Run campaign**.

### Environment variables

| Variable | Purpose |
|----------|---------|
| `AI_FRONTER_GPU_HOST` | Override GPU IP |
| `AI_FRONTER_MEDIA_PORT` | Fixed worker port (skip lookup) |
| `AI_FRONTER_CONFIG` | Path to JSON config |
| `AI_FRONTER_EAGI_FORMAT` | `slin` (default) or `ulaw` for EAGI fd 3 |
| `AI_FRONTER_LOG` | e.g. `/var/log/ai-fronter-bridge.log` |
| `AI_FRONTER_WS_TIMEOUT` | WebSocket connect timeout (default 8s) |

## Asterisk dialplan

See `extensions_ai_fronter.conf.example`. One EAGI stanza per ViciDial agent login:

```ini
exten => 6666,1,NoOp(AI Fronter bot 6666)
 same => n,Answer()
 same => n,EAGI(/usr/local/bin/ai-fronter-bridge.py,6666)
 same => n,Hangup()
```

Reload dialplan after editing:

```bash
asterisk -rx "dialplan reload"
```

### ViciDial wiring

1. **Admin → Remote Agents** — set each AI bot's extension to match dialplan (e.g. `6666`)
2. Dashboard **Assign bot** — set the same value in **ViciDial agent login**
3. **Run campaign** — GPU supervisor starts worker on port 8800/8801/8802
4. ViciDial auto-dialer **ACTIVE** with leads in hopper
5. Answered call → agent extension → EAGI → GPU WebSocket → AI qualifies → warm transfer

Map each `vicidial_agent_user` → `media_port` (from `curl http://GPU_IP:8770/status`).

## Firewall

Open on GPU (Vast.ai):

| Port | Purpose |
|------|---------|
| 8770 | Fleet supervisor `/health`, `/sync`, `/status` |
| 8800–8802 | Worker media WebSockets (one per bot) |

Allow inbound from **BPO ViciDial server IP** only.

## Verify worker is ready

```bash
curl http://GPU_IP:8800/health
# {"ok":"true","bot_id":"...","agent_user":"6666",...}
```

```bash
curl http://GPU_IP:8770/status
# lists workers with vicidial_agent_user + media_port
```

## Verify ViciDial API from GPU

```bash
curl "http://VICIDIAL_IP/agc/api.php?source=ai-fronter&user=APIUSER&pass=PASS&function=version"
```

## Alternative setups

### Option B — SIP trunk to GPU

Register each bot as a SIP extension pointing at your GPU SIP listener (advanced — not included in pilot).

### Option C — Telnyx middle layer

ViciDial → SIP → Telnyx → GPU Telnyx server (works for tests, adds latency/cost).

## After bridge works

1. BPO clicks **Run campaign** in dashboard
2. Supervisor starts workers → ViciDial agents mapped to campaign
3. ViciDial auto-dialer runs (campaign must be ACTIVE in ViciDial)
4. Answered call → EAGI → GPU WebSocket → AI qualifies → warm transfer to closer

## Troubleshooting

| Symptom | Check |
|---------|--------|
| `no GPU port for agent` | Run campaign first; verify `/status` lists agent; fix `agent_port_map.json` |
| `GPU unreachable` | Firewall 8800–8802 from dialer IP; `curl http://GPU:8800/health` |
| No bot audio | Run EAGI **directly** on customer channel (138368→ai-fronter-route), not `Dial(Local/6666)`; use `AI_FRONTER_EAGI_FORMAT=ulaw`; check `/var/log/ai-fronter-bridge.log` for "EAGI wrote first bot audio" |
| Call drops immediately | Worker not running; duplicate session; check `/tmp/vicidial_events.log` on GPU |
