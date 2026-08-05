#!/usr/bin/env bash
# Restore ai-fronter-bridge.py on ViciDial when SSH from PC is blocked.
# Upload agi_bridge.py.gz.b64 to /tmp/ on the dialer, then:
#   bash restore_bridge.sh
set -euo pipefail

SRC="${1:-/tmp/agi_bridge.py.gz.b64}"
DEST="/usr/local/bin/ai-fronter-bridge.py"

if [[ ! -s "$SRC" ]]; then
  echo "Missing blob: $SRC"
  echo "Upload agi_bridge.py.gz.b64 from your PC via MobaXterm SFTP to /tmp/"
  exit 1
fi

base64 -d "$SRC" | gzip -d > "$DEST"
chmod +x "$DEST"
python3 -m py_compile "$DEST"
lines="$(wc -l < "$DEST")"
echo "Restored $DEST ($lines lines)"
head -2 "$DEST"
