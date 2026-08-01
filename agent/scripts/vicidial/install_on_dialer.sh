#!/usr/bin/env bash
# Install AI Fronter AGI bridge on a ViciDial/Asterisk server (run as root).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_BIN="/usr/local/bin/ai-fronter-bridge.py"
CONFIG_DIR="/etc/ai-fronter"
CONFIG_FILE="${CONFIG_DIR}/agent_port_map.json"

echo "==> Installing ai-fronter-bridge.py"
install -m 0755 "${SCRIPT_DIR}/agi_bridge.py" "${INSTALL_BIN}"

echo "==> Installing config"
mkdir -p "${CONFIG_DIR}"
if [[ ! -f "${CONFIG_FILE}" ]]; then
  install -m 0644 "${SCRIPT_DIR}/agent_port_map.json.example" "${CONFIG_FILE}"
  echo "    Created ${CONFIG_FILE} — edit gpu_host and agents map"
else
  echo "    Kept existing ${CONFIG_FILE}"
fi

echo "==> Installing Python dependency"
if command -v pip3 >/dev/null 2>&1; then
  pip3 install --upgrade websocket-client
else
  echo "WARNING: pip3 not found — install websocket-client manually"
fi

echo ""
echo "Done. Next steps:"
echo "  1. Edit ${CONFIG_FILE}"
echo "  2. Add dialplan from extensions_ai_fronter.conf.example"
echo "  3. asterisk -rx 'dialplan reload'"
echo "  4. ${INSTALL_BIN} --test-ws 6666"
