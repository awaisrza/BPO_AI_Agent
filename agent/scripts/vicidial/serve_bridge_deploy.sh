#!/usr/bin/env bash
# Run on the GPU box — serves agi_bridge.py + bootstrap script for ViciDial curl install.
#
#   cd /workspace/BPO_AI_Agent/agent/scripts/vicidial
#   bash serve_bridge_deploy.sh
#
# Then map a Vast public port → DEPLOY_PORT (default 10100), e.g. 53513 → 10100.
# On ViciDial:
#   DEPLOY_URL=http://79.116.54.219:53513 bash bootstrap_audiosocket_bridge.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_PORT="${DEPLOY_PORT:-10100}"
PID_FILE="/tmp/ai-fronter-bridge-deploy.pid"

if [[ ! -f "${SCRIPT_DIR}/agi_bridge.py" ]]; then
  echo "Missing ${SCRIPT_DIR}/agi_bridge.py"
  exit 1
fi

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "Deploy server already running (pid $(cat "$PID_FILE")) on port ${DEPLOY_PORT}"
  echo "Files:"
  echo "  http://0.0.0.0:${DEPLOY_PORT}/agi_bridge.py"
  echo "  http://0.0.0.0:${DEPLOY_PORT}/bootstrap_audiosocket_bridge.sh"
  exit 0
fi

cd "$SCRIPT_DIR"
nohup python3 -m http.server "$DEPLOY_PORT" --bind 0.0.0.0 >> /tmp/bridge-deploy.log 2>&1 &
echo $! > "$PID_FILE"
sleep 1

if [[ -f "${SCRIPT_DIR}/agi_bridge.py.gz.b64" ]]; then
  echo "Also serving agi_bridge.py.gz.b64 (compressed fallback)"
fi

if curl -fsS "http://127.0.0.1:${DEPLOY_PORT}/agi_bridge.py" | head -1 | grep -q python; then
  echo "Deploy server OK on port ${DEPLOY_PORT}"
  wc -l "${SCRIPT_DIR}/agi_bridge.py"
  grep -c serve.audiosocket "${SCRIPT_DIR}/agi_bridge.py" || true
  echo ""
  echo "Map Vast public port → ${DEPLOY_PORT}, then on ViciDial run:"
  echo "  curl -fsSL http://YOUR_GPU_PUBLIC_IP:PUBLIC_PORT/bootstrap_audiosocket_bridge.sh | bash"
  echo "  # or:"
  echo "  DEPLOY_URL=http://YOUR_GPU_PUBLIC_IP:PUBLIC_PORT bash bootstrap_audiosocket_bridge.sh"
else
  echo "Deploy server failed — see /tmp/bridge-deploy.log"
  exit 1
fi
