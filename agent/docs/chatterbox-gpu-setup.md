# Chatterbox + GPU setup (RunPod)

One stack for pilot through scale: **faster-whisper + Chatterbox Turbo + Gemini** on a single NVIDIA L4 pod.

## What you need before starting

| Item | Details |
|------|---------|
| RunPod account | https://runpod.io |
| Reference WAV | 10–20 s US female fronter (`agent/models/sarah-reference.wav`) |
| Env keys | `GOOGLE_API_KEY`, Supabase keys (campaign script) |
| Budget | ~**$70/mo** pod (8 hr dial shift) for 2–40 bots |

Voice clone on self-hosted Chatterbox is **free** — no Resemble cloud fees.

---

## Step 1 — Record reference audio

1. Record or export **10–20 seconds** of calm US English (female fronter).
2. Save as **`agent/models/sarah-reference.wav`** (mono or stereo, WAV).
3. Example line to record:

   > "Hi, this is Sarah on a recorded line. Do you have a quick moment to talk about Medicare?"

Tips: quiet room, no music, natural pace — like a real dialer call.

---

## Step 2 — Create RunPod GPU pod

1. RunPod → **Pods** → **Deploy**
2. Pick **NVIDIA L4 (24 GB)** — US region if possible
3. Template: **RunPod PyTorch 2.x** (CUDA 12+)
4. Disk: **≥ 40 GB** (model weights)
5. Start pod → note **SSH** and **Jupyter/Terminal** access

---

## Step 3 — Install on the pod

SSH into the pod, then:

```bash
# Clone your repo (or upload agent/ folder)
git clone YOUR_REPO_URL ai-fronter
cd ai-fronter/agent

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements-gpu.txt
# PyAudio for mic test (optional on server)
apt-get update && apt-get install -y portaudio19-dev
pip install pyaudio
```

Upload reference WAV if not in repo:

```bash
mkdir -p models
# scp from laptop: agent/models/sarah-reference.wav → pod:~/ai-fronter/agent/models/
```

---

## Step 4 — Environment (`.env.local`)

Create `agent/.env.local` on the pod:

```env
VOICE_BACKEND=chatterbox

WHISPER_MODEL=distil-large-v2
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=int8_float16

CHATTERBOX_REFERENCE_AUDIO=/workspace/ai-fronter/agent/models/sarah-reference.wav
CHATTERBOX_DEVICE=cuda
CHATTERBOX_EXAGGERATION=0.35
CHATTERBOX_CFG_WEIGHT=0.5

GOOGLE_API_KEY=your-key
GEMINI_MODEL=gemini-2.5-flash-lite

NEXT_PUBLIC_SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# Phone test (optional)
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=+1xxxxxxxxxx
LOCAL_SERVER_URL=https://your-tunnel.ngrok-free.app
```

Also copy keys from `dashboard/.env.local` on your laptop if easier.

---

## Step 5 — Test Chatterbox (voice only)

First run downloads Chatterbox + Whisper weights (~2–5 min):

```bash
cd agent
source .venv/bin/activate

python scripts/test_chatterbox.py --text "Hi, this is Sarah on a recorded line."
```

Output: `agent/chatterbox-out/line.wav` — listen before going live.

Test full Medicare script:

```bash
python scripts/test_chatterbox.py \
  --campaign-id 4c3aaed2-2dc6-4828-9d19-1024636dc0ac \
  --all
```

---

## Step 6 — Live mic test (full pipeline)

On the pod (with mic) or your Windows machine with NVIDIA GPU:

```bash
python -m app.main --live --campaign-id YOUR-CAMPAIGN-UUID
```

Speak as the lead. Bot should greet from cached script lines, respond in ~1 s on script turns.

---

## Step 7 — Phone test (Twilio)

1. Expose port **8765** (RunPod TCP proxy or ngrok on pod)
2. Set `LOCAL_SERVER_URL` in `.env.local`
3. Run:

```bash
python -m app.main --phone \
  --campaign-id YOUR-CAMPAIGN-UUID \
  --dial +923142222318
```

---

## Step 8 — Run multiple bots on one pod

One L4 handles **~3 concurrent** lines comfortably for pilot; **~40** at scale.

Start one agent process per concurrent line (different terminal or systemd service):

```bash
# Bot 1
python -m app.main --phone --campaign-id UUID --dial +1...

# Bot 2 (another shell)
python -m app.main --phone --campaign-id UUID --dial +1...
```

Stop the pod when the BPO shift ends to save money.

---

## Windows (local NVIDIA GPU) — dev only

Same env, but paths for Windows:

```powershell
cd agent
.\.venv\Scripts\python.exe -m pip install -r requirements-gpu.txt

# Put reference at agent\models\sarah-reference.wav
.\.venv\Scripts\python.exe scripts\test_chatterbox.py --text "Hi, this is Sarah."

.\.venv\Scripts\python.exe -m app.main --live --campaign-id YOUR-UUID
```

Without NVIDIA GPU, use RunPod — Chatterbox on CPU is too slow for live calls.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `CUDA out of memory` | Use `distil-large-v2` not `large-v3`; one pod per 3–5 concurrent calls |
| `reference audio not found` | Set `CHATTERBOX_REFERENCE_AUDIO` to absolute path |
| First call very slow | Normal — models load once; script cache warms at startup |
| Robotic sound | Lower `CHATTERBOX_EXAGGERATION` to `0.25`; shorten script lines |
| STT wrong language | English Medicare — keep `distil-large-v2` |
| `chatterbox-tts` import error | `pip install chatterbox-tts torch torchaudio` |

---

## Cost reminder @ 3,500 min/bot/month

| Bots on 1× L4 | ~$/bot/month |
|---------------|--------------|
| 3 (pilot) | ~$35–42 |
| 10 | ~$14–20 |
| 40 | ~$7–13 |

Gemini + GPU share dominate; Chatterbox clone stays **$0**.

---

## Checklist before BPO handoff

- [ ] Reference WAV sounds like a real fronter
- [ ] `test_chatterbox.py --all` passes for Medicare campaign
- [ ] 10+ `--phone` or `--live` test calls end-to-end
- [ ] KB entries for top objections in dashboard
- [ ] Pod starts automatically before shift (or manual runbook)
- [ ] Fish/Deepgram keys **not required** — `VOICE_BACKEND=chatterbox` only
