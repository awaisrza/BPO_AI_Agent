#!/usr/bin/env bash
# Pre-call check for the GPU box: pull code, restart inference pool + supervisor,
# wait until Whisper/Chatterbox and the ViciDial worker are really ready, then
# run a TTS -> STT round trip. Prints READY only when a call can succeed.
#
#   bash scripts/preflight_gpu.sh            # pull + restart + verify
#   bash scripts/preflight_gpu.sh --no-pull  # restart + verify only
#   bash scripts/preflight_gpu.sh --check    # verify only (no restart)
set -uo pipefail
cd "$(dirname "$0")/.."

PULL=1
RESTART=1
for arg in "$@"; do
  case "$arg" in
    --no-pull) PULL=0 ;;
    --check) PULL=0; RESTART=0 ;;
  esac
done

if [ -f .venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi
if [ -f .env.local ]; then
  set -a
  # shellcheck disable=SC1091
  source .env.local
  set +a
fi

POOL_PORT="${INFERENCE_POOL_PORT:-8780}"
MEDIA_PORT="${FLEET_MEDIA_BASE_PORT:-10200}"
SUP_PORT="${SUPERVISOR_PORT:-8770}"
FAIL=0

ok()   { echo "  [OK]   $*"; }
bad()  { echo "  [FAIL] $*"; FAIL=1; }
step() { echo; echo "=== $* ==="; }

if [ "$PULL" = 1 ]; then
  step "1. git pull"
  (cd .. && git pull --ff-only) || bad "git pull failed (fix before calling)"
fi
echo "  code: $(cd .. && git rev-parse --short HEAD) on $(cd .. && git branch --show-current)"

if [ "$RESTART" = 1 ]; then
  step "2. restart inference pool + supervisor + worker"
  pkill -9 -f app.inference_pool 2>/dev/null || true
  sleep 2
  bash scripts/restart_fleet_supervisor.sh >/tmp/preflight_restart.log 2>&1 || true
  ok "restart issued (details: /tmp/preflight_restart.log)"
fi

step "3. wait for inference pool (Whisper + Chatterbox), up to 5 min"
deadline=$((SECONDS + 300))
pool_ok=0
while [ $SECONDS -lt $deadline ]; do
  body=$(curl -s --max-time 3 "http://127.0.0.1:${POOL_PORT}/health" || true)
  if echo "$body" | grep -q '"ok":true' && echo "$body" | grep -q '"whisper_loaded":true'; then
    pool_ok=1
    break
  fi
  if [ "$RESTART" = 1 ] && [ $((SECONDS % 30)) -lt 3 ]; then
    curl -s -X POST --max-time 5 "http://127.0.0.1:${SUP_PORT}/sync" >/dev/null 2>&1 || true
  fi
  sleep 3
done
if [ "$pool_ok" = 1 ]; then ok "pool ready: $body"; else bad "pool not ready: ${body:-no response}"; tail -20 /tmp/inference_pool.log; fi

step "4. wait for ViciDial worker on :${MEDIA_PORT}, up to 3 min"
deadline=$((SECONDS + 180))
worker_ok=0
while [ $SECONDS -lt $deadline ]; do
  body=$(curl -s --max-time 3 "http://127.0.0.1:${MEDIA_PORT}/health" || true)
  if echo "$body" | grep -q '"ready":true'; then
    worker_ok=1
    break
  fi
  sleep 3
done
if [ "$worker_ok" = 1 ]; then ok "worker ready: $body"; else bad "worker not ready: ${body:-no response}"; tail -20 /tmp/supervisor.log; fi

step "5. speech round trip (TTS -> STT)"
if [ "$pool_ok" = 1 ]; then
  python - "$POOL_PORT" <<'PY' || FAIL=1
import io, sys, time, wave
import httpx

base = f"http://127.0.0.1:{sys.argv[1]}"
phrase = "Yes, I am sixty five years old."
t0 = time.monotonic()
pcm = httpx.post(f"{base}/v1/tts", json={"text": phrase, "sample_rate": 16000, "telephony": True}, timeout=120).content
t_tts = time.monotonic() - t0
if len(pcm) < 3200:
    print(f"  [FAIL] TTS returned {len(pcm)} bytes")
    sys.exit(1)
buf = io.BytesIO()
with wave.open(buf, "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(pcm)
t0 = time.monotonic()
r = httpx.post(f"{base}/v1/stt", content=buf.getvalue(),
               params={"no_speech_prob": "0.5", "telephony": "true"}, timeout=60)
t_stt = time.monotonic() - t0
text = r.json().get("text", "")
print(f"  TTS {t_tts:.1f}s ({len(pcm)} bytes), STT {t_stt:.1f}s -> {text!r}")
if "65" in text or "sixty" in text.lower():
    print("  [OK]   Whisper understood the bot's own voice")
else:
    print("  [FAIL] Whisper did not understand a clean phrase")
    sys.exit(1)
PY
else
  bad "skipped (pool not ready)"
fi

step "6. diagnostics"
grep -q '^STT_DUMP_DIR=' .env.local 2>/dev/null && ok "STT_DUMP_DIR=$(grep '^STT_DUMP_DIR=' .env.local | cut -d= -f2) (caller segments saved)" || echo "  [info] STT_DUMP_DIR not set (caller audio not saved)"
pgrep -af app.inference_pool | head -1 | sed 's/^/  pool: /'
pgrep -af app.fleet_worker | head -3 | sed 's/^/  worker: /'
df -h / | tail -1 | awk '{print "  disk: "$5" used"}'

echo
if [ "$FAIL" = 0 ]; then
  echo "##########  GPU READY — run the ViciDial preflight, then dial  ##########"
else
  echo "##########  GPU NOT READY — do not dial; paste this output  ##########"
  exit 1
fi
