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

### Live mic test (full voice pipeline)

Requires API keys in `dashboard/.env.local` or `agent/.env.local`.

```powershell
.\.venv\Scripts\python.exe -m pip install "pipecat-ai[deepgram,local,silero]" pyaudio

.\.venv\Scripts\python.exe -m app.main --live
```

Speak into your mic. The bot greets you, follows the script, answers off-script questions via Gemini, then transfers or hangs up. Ctrl-C to quit.

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
| `app/vicidial.py` | ViciDial API client — disposition + warm transfer                         |
| `app/pipeline.py` | Builds the Pipecat pipeline from the above                                 |
| `app/main.py`     | Entrypoint                                                                 |

## Why the FSM is separate

Most of a fronter call is deterministic (greet → pitch → qualify → transfer). Keeping that as a pure
state machine makes it **testable** and means the LLM is only called for off-script turns — which is
also the cheapest, lowest-latency design.

## Test

```bash
pytest
```
