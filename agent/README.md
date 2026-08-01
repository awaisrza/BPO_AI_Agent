# agent — AI fronter voice pipeline

Pipecat pipeline: **VAD → STT → conversation FSM (+ Gemini for off-script) → TTS**, wired to ViciDial
for dispositions and warm transfers.

## Run

### Windows (PowerShell)

```powershell
cd agent
python -m venv .venv
```

**Activate the venv** — pick one:

```powershell
# Option A (easiest): skip activate, call venv python directly
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m app.main

# Option B: use the .bat activator (works even when scripts are blocked)
.\.venv\Scripts\activate.bat

# Option C: allow PowerShell scripts once (CurrentUser only, safe)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\.venv\Scripts\Activate.ps1
```

If `pip install -r requirements.txt` is slow or fails, install simulation deps only:

```powershell
.\.venv\Scripts\python.exe -m pip install httpx python-dotenv pydantic loguru pytest pytest-asyncio
```

Put API keys in **`agent/.env.local`** or **`dashboard/.env.local`** (same file as Supabase is fine).

### Test APIs (after keys are in `.env.local`)

```powershell
.\.venv\Scripts\python.exe -m pip install httpx python-dotenv google-generativeai

# One at a time
.\.venv\Scripts\python.exe scripts/test_fish.py
.\.venv\Scripts\python.exe scripts/test_gemini.py
.\.venv\Scripts\python.exe scripts/test_deepgram.py

# Or all three
.\.venv\Scripts\python.exe scripts/test_all.py
```

`test_fish_balance.py` — check API wallet (separate from platform credits).
`test_fish_voices.py` — list valid voice IDs if you get "Reference not found".
`test_fish.py` saves `greeting.mp3` in `agent/` — play it to hear your voice.
`test_deepgram.py` uses `test.wav` if present, else a public Deepgram sample.

### Test your script with Piper (local, free)

One-time setup:

1. Download [piper_windows_amd64.zip](https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip) → extract to `C:\piper\`
2. Download both files into `C:\piper\models\`:
   - [en_US-libritts-high.onnx](https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/libritts/high/en_US-libritts-high.onnx)
   - [en_US-libritts-high.onnx.json](https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/libritts/high/en_US-libritts-high.onnx.json)
3. Add to `agent/.env.local`:

```env
PIPER_EXE=C:\piper\piper.exe
PIPER_MODEL=C:\piper\models\en_US-libritts-high.onnx
PIPER_SPEAKER=0
```

Then test your lines:

```powershell
# One custom line
.\.venv\Scripts\python.exe scripts/test_piper.py --text "Hi, this is Sarah on a recorded line."

# Try another speaker (0 = best female, 1 = second-best)
.\.venv\Scripts\python.exe scripts/test_piper.py --text "..." --speaker 1

# All script lines from a JSON file (greeting, pitch, qualifiers, transfer, hangup)
.\.venv\Scripts\python.exe scripts/test_piper.py --script-file my-script.json --all

# All lines from a dashboard campaign (needs Supabase keys in .env.local)
.\.venv\Scripts\python.exe scripts/test_piper.py --campaign-id YOUR-CAMPAIGN-UUID --all
```

WAV files land in `agent/piper-out/`. Play with `start agent\piper-out\greeting.wav`.

### Live mic test (full voice pipeline)

Requires API keys in `dashboard/.env.local` or `agent/.env.local`.

**Managed backend (default)** — Deepgram + Fish, no GPU:

```powershell
.\.venv\Scripts\python.exe -m pip install "pipecat-ai[deepgram,local,silero]" pyaudio

.\.venv\Scripts\python.exe -m app.main --live
```

**GPU backend** — faster-whisper STT + Piper TTS. Add to `.env.local`:

```env
VOICE_BACKEND=gpu
WHISPER_DEVICE=cuda
WHISPER_MODEL=distil-large-v2
PIPER_EXE=C:\piper\piper.exe
PIPER_MODEL=C:\piper\models\en_US-libritts-high.onnx
GOOGLE_API_KEY=...
```

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-gpu.txt pyaudio
.\.venv\Scripts\python.exe -m app.main --live --campaign-id YOUR-CAMPAIGN-UUID
```

Static script lines are pre-cached at startup. Off-script Gemini replies use live Piper synthesis.

On Windows without CUDA, use `WHISPER_DEVICE=cpu` to test Piper + cache (STT will be slow).

### GPU production (RunPod)

One **L4/A10** pod with `VOICE_BACKEND=gpu`: faster-whisper on CUDA, Piper TTS, Gemini stays cloud. ~40–50 bots per mid GPU. See `docs/architecture.md` for unit economics.

Speak into your mic. The bot greets you, follows the script, answers off-script questions via Gemini, then transfers or hangs up. Ctrl-C to quit.

### Real phone test (Twilio PSTN)

Same pipeline as `--live`, but audio goes over a **real phone call** to your cell. Works with managed or GPU backend; no ViciDial required.

**1. Twilio setup** (one time)

- Create a [Twilio](https://www.twilio.com) account (~$15 trial credit)
- Buy a voice number (US ~$1/mo)
- Copy **Account SID**, **Auth Token**, and your **From** number

**2. Expose your laptop** (Twilio webhooks need a public URL)

Winget installs ngrok but may not add it to PATH. Use the helper script:

```powershell
cd agent
.\scripts\start-tunnel.ps1
```

Or run ngrok directly (full path on Windows after winget install):

```powershell
& "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe\ngrok.exe" http 8765
```

First time only — sign up at https://dashboard.ngrok.com and run:

```powershell
& "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe\ngrok.exe" config add-authtoken YOUR_TOKEN
```

Alternative (no ngrok account): `winget install Cloudflare.cloudflared` then `cloudflared tunnel --url http://localhost:8765`

Copy the `https://....ngrok-free.app` URL.

**3. Add to `dashboard/.env.local`**

```env
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM_NUMBER=+1xxxxxxxxxx
LOCAL_SERVER_URL=https://xxxx.ngrok-free.app
```

**4. Install phone deps**

```powershell
.\.venv\Scripts\python.exe -m pip install fastapi "uvicorn[standard]" twilio
```

**5. Run — bot calls your phone**

```powershell
.\.venv\Scripts\python.exe -m app.main --phone --campaign-id YOUR-CAMPAIGN-UUID --dial +14155551234
```

Answer the call. You are the "lead" — talk to the bot on your phone like a real outbound call.

**Or inbound:** set your Twilio number's voice webhook to `{LOCAL_SERVER_URL}/twiml`, start `--phone` without `--dial`, then call your Twilio number from any phone.

**Or dial later via API:**

```powershell
curl -X POST http://localhost:8765/dialout -H "Content-Type: application/json" -d "{\"to_number\":\"+14155551234\"}"
```

> **ViciDial production:** Fleet supervisor + workers + warm transfer are implemented. BPO IT must wire the audio AGI bridge from ViciDial to GPU worker ports — see `docs/vicidial-flow.md` and `scripts/vicidial/README.md`. Use Telnyx phone test to validate script + voice first.

### Load script from dashboard (Supabase)

1. Add to `dashboard/.env.local` (same file as API keys):
   ```env
   SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
   ```
   Get it from Supabase → **Project Settings → API → service_role** (secret — never commit).

2. List campaign/bot IDs:
   ```powershell
   .\.venv\Scripts\python.exe scripts\list_supabase.py
   ```

3. Run with your campaign script:
   ```powershell
   .\.venv\Scripts\python.exe -m app.main --live --campaign-id YOUR-CAMPAIGN-UUID
   ```
   Or via assigned bot:
   ```powershell
   .\.venv\Scripts\python.exe -m app.main --live --bot-id YOUR-BOT-UUID
   ```

Edit script in dashboard → **Campaigns → Save** → re-run the agent command (loads fresh each start).

### macOS / Linux

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.main
```

## Modules

| File              | Responsibility                                                            |
| ----------------- | ------------------------------------------------------------------------- |
| `app/config.py`   | Env-backed settings + script config loading                               |
| `app/conversation.py` | Pure conversation state machine (testable, no Pipecat dependency)     |
| `app/fish_tts.py` | Custom Pipecat TTS service backed by the Fish Audio API                    |
| `app/piper_tts.py` | Local Piper TTS + script-line cache (GPU backend)                       |
| `app/piper_paths.py` | Piper binary/model resolution and synthesis helpers                     |
| `app/vicidial.py` | ViciDial API client — disposition + warm transfer                         |
| `app/pipeline.py` | Builds the Pipecat pipeline from the above                                 |
| `app/phone_server.py` | Twilio phone-test server (real PSTN calls)                           |
| `app/main.py`     | Entrypoint                                                                 |

## Why the FSM is separate

Most of a fronter call is deterministic (greet → pitch → qualify → transfer). Keeping that as a pure
state machine makes it **testable** and means the LLM is only called for off-script turns — which is
also the cheapest, lowest-latency design.

## Test

```bash
pytest
```
