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

Copy `cp .env.example .env` (fill API keys later — not needed for text simulation).

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
