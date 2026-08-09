#!/usr/bin/env bash
# Clean restart: kill by port, then one supervisor + worker.
# Vast.ai: map PUBLIC 53604 → INTERNAL 8770, PUBLIC 53512 → INTERNAL 10200.
set -euo pipefail
cd "$(dirname "$0")/.."

MEDIA_PORT="${FLEET_MEDIA_BASE_PORT:-10200}"
SUP_PORT="${SUPERVISOR_PORT:-8770}"

echo "=== stopping fleet processes ==="
pkill -9 -f run_supervisor 2>/dev/null || true
pkill -9 -f 'app.fleet_worker' 2>/dev/null || true
pkill -9 -f 'app.fleet_supervisor' 2>/dev/null || true
sleep 2

# Include 8800 — stale workers from before FLEET_MEDIA_BASE_PORT=10200
for port in "$SUP_PORT" "$MEDIA_PORT" 8800; do
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${port}/tcp" 2>/dev/null || true
  fi
  if command -v lsof >/dev/null 2>&1; then
    pids=$(lsof -t -iTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)
    if [ -n "${pids:-}" ]; then
      echo "kill -9 PIDs on port ${port}: ${pids}"
      kill -9 ${pids} 2>/dev/null || true
    fi
  fi
done
sleep 1

echo "=== ports (should be empty for ${SUP_PORT}, ${MEDIA_PORT}, 8800) ==="
ss -tlnp | grep -E "${SUP_PORT}|${MEDIA_PORT}|8800" || echo "(free)"

export FLEET_MEDIA_BASE_PORT="$MEDIA_PORT"
export SUPERVISOR_PORT="$SUP_PORT"

echo "=== starting supervisor (media=${MEDIA_PORT}, supervisor=${SUP_PORT}) ==="
echo "    Vast must map public 53604 -> internal ${SUP_PORT}, public 53512 -> internal ${MEDIA_PORT}"
nohup python run_supervisor.py > /tmp/supervisor.log 2>&1 &
sleep 20

echo "=== processes ==="
pgrep -af run_supervisor || echo "NO SUPERVISOR"
pgrep -af fleet_worker || echo "NO WORKER"

echo "=== health ==="
curl -sf "http://127.0.0.1:${SUP_PORT}/health" && echo " supervisor OK" || echo " supervisor FAIL"
curl -sf "http://127.0.0.1:${MEDIA_PORT}/health" && echo " worker OK" || echo " worker FAIL (may still prewarm)"

echo "=== supervisor log ==="
tail -20 /tmp/supervisor.log
