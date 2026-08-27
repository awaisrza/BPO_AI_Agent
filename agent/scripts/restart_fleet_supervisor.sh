#!/usr/bin/env bash
# Clean restart: kill by port, then one supervisor + worker.
# Vast.ai: map PUBLIC 53604 → INTERNAL 8770, PUBLIC 53512 → INTERNAL 10200.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -f .env.local ]; then
  set -a
  # shellcheck disable=SC1091
  source .env.local
  set +a
fi

MEDIA_PORT="${FLEET_MEDIA_BASE_PORT:-10200}"
SUP_PORT="${SUPERVISOR_PORT:-8770}"

echo "=== stopping fleet processes ==="
pkill -9 -f run_supervisor 2>/dev/null || true
pkill -9 -f 'app.fleet_worker' 2>/dev/null || true
pkill -9 -f 'app.fleet_supervisor' 2>/dev/null || true
pkill -9 -f 'uvicorn.*fleet_supervisor' 2>/dev/null || true
sleep 2

# Include 8800 — stale workers from before FLEET_MEDIA_BASE_PORT=10200
# Vast often lacks fuser/lsof; also parse ss when port stays busy (Errno 98).
_kill_port() {
  local port="$1"
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
  if command -v ss >/dev/null 2>&1; then
    # ss -tlnp: users:(("python",pid=1234,fd=...))
    pids=$(ss -tlnp 2>/dev/null | awk -v p=":${port}" '
      index($0, p) {
        while (match($0, /pid=[0-9]+/)) {
          print substr($0, RSTART+4, RLENGTH-4)
          $0 = substr($0, RSTART+RLENGTH)
        }
      }' | sort -u)
    if [ -n "${pids:-}" ]; then
      echo "kill -9 ss PIDs on port ${port}: ${pids}"
      # shellcheck disable=SC2086
      kill -9 ${pids} 2>/dev/null || true
    fi
  fi
  # Vast sometimes hides pids from ss -tlnp; fall back to /proc inode walk.
  python3 - "$port" <<'PY' 2>/dev/null || true
import os, sys
port = int(sys.argv[1])
want = f"{port:04X}"
inodes = set()
for path in ("/proc/net/tcp", "/proc/net/tcp6"):
    try:
        lines = open(path).read().splitlines()[1:]
    except OSError:
        continue
    for line in lines:
        parts = line.split()
        if len(parts) < 10:
            continue
        local = parts[1]
        if local.endswith(":" + want) and parts[3] == "0A":  # LISTEN
            inodes.add(parts[9])
if not inodes:
    raise SystemExit(0)
killed = []
for pid in os.listdir("/proc"):
    if not pid.isdigit():
        continue
    fd_dir = f"/proc/{pid}/fd"
    try:
        for fd in os.listdir(fd_dir):
            try:
                target = os.readlink(f"{fd_dir}/{fd}")
            except OSError:
                continue
            if target.startswith("socket:[") and target[8:-1] in inodes:
                os.kill(int(pid), 9)
                killed.append(pid)
                break
    except OSError:
        continue
if killed:
    print(f"kill -9 /proc PIDs on port {port}: {' '.join(killed)}")
PY
}

for port in "$SUP_PORT" "$MEDIA_PORT" 8800; do
  _kill_port "$port"
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
