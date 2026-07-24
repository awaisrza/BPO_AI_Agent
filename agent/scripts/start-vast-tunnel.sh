#!/usr/bin/env bash
# Run ON the Vast GPU instance — exposes localhost to Telnyx as wss:// (required for media).
#
# Telnyx media streams need secure WebSocket (wss:// on port 443). Vast's mapped
# http://IP:31359 → ws:// often connects briefly then drops (choppy / robotic audio).
#
# Usage (two terminals on the GPU):
#   Terminal 1:  ./scripts/start-vast-tunnel.sh
#   Terminal 2:  set LOCAL_SERVER_URL to the https URL printed below, then run_telnyx.py
#
# Requires cloudflared (free, no account):
#   curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared
#   chmod +x /usr/local/bin/cloudflared

set -euo pipefail

PORT="${AGENT_PORT:-10100}"
HOST="${AGENT_HOST:-127.0.0.1}"
if [[ "$HOST" == "0.0.0.0" || "$HOST" == "::" ]]; then
  HOST="127.0.0.1"
fi

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared not found. Install:"
  echo "  curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared"
  echo "  chmod +x /usr/local/bin/cloudflared"
  exit 1
fi

echo "=== Vast telephony tunnel ==="
echo "Forwarding https/wss (cloudflare) -> http://${HOST}:${PORT}"
echo ""
echo "When cloudflared prints a URL like https://xxxx.trycloudflare.com:"
echo "  1. Put it in agent/.env.local:"
echo "       LOCAL_SERVER_URL=https://xxxx.trycloudflare.com"
echo "  2. Restart run_telnyx.py (keep this tunnel running)."
echo "  3. Do NOT use http://VAST_IP:31359 — that is ws:// and causes choppy calls."
echo ""

exec cloudflared tunnel --url "http://${HOST}:${PORT}"
