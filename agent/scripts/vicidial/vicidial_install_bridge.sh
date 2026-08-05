#!/usr/bin/env bash
# Install agi_bridge from GPU deploy server onto ViciDial. Run on ViciDial as root.
# Usage: DEPLOY_PORT=53513 bash vicidial_install_bridge.sh
set -euo pipefail

GPU_HOST="${GPU_HOST:-79.116.54.219}"
DEPLOY_PORT="${DEPLOY_PORT:-10100}"
DEPLOY_URL="${DEPLOY_URL:-http://${GPU_HOST}:${DEPLOY_PORT}}"
AGENT="${AI_FRONTER_AGENT_USER:-6666}"
INSTALL_BIN="/usr/local/bin/ai-fronter-bridge.py"

echo "==> Fetch ${DEPLOY_URL}/agi_bridge.py"
curl -fsSL "${DEPLOY_URL}/agi_bridge.py" -o /tmp/agi_bridge_new.py
wc -l /tmp/agi_bridge_new.py
grep serve-audiosocket /tmp/agi_bridge_new.py | head -1
python3 -m py_compile /tmp/agi_bridge_new.py

/bin/cp -f /tmp/agi_bridge_new.py "$INSTALL_BIN"
chmod +x "$INSTALL_BIN"
pip3 install -q websocket-client 2>/dev/null || true

pkill -f "serve-audiosocket" 2>/dev/null || true
sleep 1
nohup python3 "$INSTALL_BIN" --serve-audiosocket "$AGENT" >> /var/log/ai-fronter-bridge.log 2>&1 &
sleep 2

ss -tlnp | grep 9092 || { tail -5 /var/log/ai-fronter-bridge.log; exit 1; }
tail -3 /var/log/ai-fronter-bridge.log
mysql asterisk -e "UPDATE vicidial_hopper SET status='READY' WHERE campaign_id='testing';" 2>/dev/null || true
echo "OK — test dial from dashboard"
