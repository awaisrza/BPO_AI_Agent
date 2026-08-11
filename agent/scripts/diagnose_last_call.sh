#!/usr/bin/env bash
# Interpret the most recent ViciDial call from GPU logs.
set -euo pipefail
LOG="${1:-/tmp/vicidial_events.log}"
AGENT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [ ! -f "$LOG" ]; then
  echo "No log at $LOG"
  exit 1
fi

echo "=== last crash tracebacks ==="
grep -n 'VICIDIAL CRASH' "$LOG" | tail -3
python3 - <<'PY' "$LOG"
import sys
from pathlib import Path
log = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
chunks = log.split("=== VICIDIAL CRASH ===")
for block in chunks[-2:]:
    block = block.strip()
    if block:
        print(block[:2500])
        print("---")
PY

echo ""
echo "=== last call events ==="
grep -E 'VICIDIAL WS handler|greeting done|VAD:|STT|CALLER:|BOT:|turn closed|queued|CRASH|timeout|END CALL' "$LOG" | tail -50

echo ""
echo "=== inference pool ==="
curl -sf http://127.0.0.1:8780/health 2>/dev/null && echo || echo "pool not reachable on :8780"
if [ -f /tmp/inference_pool.log ]; then
  grep -E 'STT failed|error|Error|Pool STT' /tmp/inference_pool.log | tail -10 || true
fi

echo ""
echo "=== fleet worker log (STT/VAD detail) ==="
WORKER_LOG="$(ls -t /tmp/fleet_worker_*.log 2>/dev/null | head -1 || true)"
if [ -n "${WORKER_LOG:-}" ]; then
  grep -E 'VAD:|STT|CALLER:|BOT:|Pooled STT|ERROR' "$WORKER_LOG" | tail -25
  echo "(full: $WORKER_LOG)"
else
  echo "no /tmp/fleet_worker_*.log"
fi

echo ""
echo "=== patch check ==="
cd "$AGENT_DIR"
python3 scripts/verify_call_patches.py 2>/dev/null || true

echo ""
echo "=== read ==="
if grep -q 'greeting done — caller turn open' "$LOG" 2>/dev/null; then
  echo "OK  caller turn opened after greeting"
else
  echo "??  no greeting-done line in last calls"
fi
if grep -q 'VAD: caller started speaking' "$LOG" 2>/dev/null; then
  echo "OK  VAD detected caller speech"
else
  echo "FAIL  no VAD lines — caller audio not reaching VAD (codec/volume?)"
fi
if grep -q 'STT heard:\|STT buffered\|CALLER:' "$LOG" 2>/dev/null; then
  echo "OK  STT transcribed caller"
else
  echo "??  no STT transcription — check inference pool + VAD"
fi
if grep -q '=== BOT:' "$LOG" 2>/dev/null; then
  echo "OK  bot generated reply"
else
  echo "??  no BOT reply line"
fi
