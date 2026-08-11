#!/usr/bin/env bash
# Interpret the most recent ViciDial call from GPU logs.
set -euo pipefail
LOG="${1:-/tmp/vicidial_events.log}"

if [ ! -f "$LOG" ]; then
  echo "No log at $LOG"
  exit 1
fi

echo "=== last call session (GPU) ==="
grep -E 'VICIDIAL WS handler|greeting done|STT|CALLER:|BOT:|turn closed|queued|CRASH|timeout|runner' "$LOG" | tail -40

echo ""
echo "=== patch check ==="
cd "$(dirname "$0")/.."
python scripts/verify_call_patches.py 2>/dev/null || echo "Run: python scripts/verify_call_patches.py"

echo ""
echo "=== read ==="
if grep -q 'greeting done — caller turn open' "$LOG" 2>/dev/null; then
  echo "OK  caller turn opened after greeting"
else
  echo "FAIL  no 'greeting done — caller turn open' — GPU missing patch_caller_reply_fix"
fi
if grep -q 'STT buffered caller text\|CALLER:' "$LOG" 2>/dev/null; then
  echo "OK  STT heard caller"
else
  echo "??  no STT/ CALLER lines — STT silent or turn still closed"
fi
if grep -q 'BOT:' "$LOG" 2>/dev/null; then
  echo "OK  bot replied"
else
  echo "??  no BOT: lines — reply never generated or TTS failed"
fi
