from pathlib import Path

root = Path(__file__).resolve().parent
b64 = (root / "agi_bridge.py.gz.b64").read_text()
header = """#!/usr/bin/env bash
# Self-contained: writes agi_bridge.py on GPU (no upload). Run on GPU as root.
set -euo pipefail
DEST="/workspace/BPO_AI_Agent/agent/scripts/vicidial/agi_bridge.py"
mkdir -p "$(dirname "$DEST")"
base64 -d <<'B64EOF' | gzip -d > "$DEST"
"""
footer = """
B64EOF
lines="$(wc -l < "$DEST")"
grep -q serve-audiosocket "$DEST" || { echo "ERROR: decode failed"; exit 1; }
echo "OK: $DEST ($lines lines)"
python3 -m py_compile "$DEST"
pkill -f "http.server 10100" 2>/dev/null || true
sleep 1
cd "$(dirname "$DEST")"
nohup python3 -m http.server 10100 --bind 0.0.0.0 >> /tmp/bridge-deploy.log 2>&1 &
sleep 1
curl -s http://127.0.0.1:10100/agi_bridge.py | head -2
echo ""
echo "Map Vast public port -> 10100, then on ViciDial: DEPLOY_PORT=YOUR_PORT bash vicidial_install_bridge.sh"
"""
(root / "gpu_install_agi_bridge.sh").write_text(header + b64 + footer, newline="\n")
print("OK", len(b64))
