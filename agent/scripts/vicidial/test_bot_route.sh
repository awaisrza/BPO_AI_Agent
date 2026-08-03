#!/usr/bin/env bash
# Run ON ViciDial server — verify customer→bot dialplan before live outbound test.
#
#   sudo bash test_bot_route.sh
#
# Expect in /var/log/asterisk/messages:
#   AI Fronter HIT ... → Dial(Local/6666 ... → EAGI → bridged to GPU

set -euo pipefail

ROOM="${ROOM:-9600666}"
AGENT="${AGENT:-6666}"

echo "==> 1) Dialplan for conference room ${ROOM}"
asterisk -rx "dialplan show ${ROOM}@default" | head -20
echo

echo "==> 2) Simulate customer entering conf room (30s) — watch logs in another terminal:"
echo "    tail -f /var/log/asterisk/messages | grep -iE 'AI Fronter|9600|6666|EAGI'"
echo

asterisk -rx "channel originate Local/${ROOM}@default/n application Wait 30" &
ORIG_PID=$!
sleep 3

echo "==> 3) Channels after originate"
asterisk -rx "core show channels verbose" | grep -iE '6666|9600|ai-fronter|EAGI|Local' || true
echo

echo "==> 4) Recent dialplan lines"
grep -iE 'AI Fronter HIT|9600666|9606666|Local/6666|EAGI|bridged to GPU' /var/log/asterisk/messages | tail -10 || true
echo

wait "$ORIG_PID" 2>/dev/null || true

echo "==> 5) GPU bridge quick test"
if [[ -x /usr/local/bin/ai-fronter-bridge.py ]]; then
  /usr/local/bin/ai-fronter-bridge.py --test-ws "${AGENT}" 2>&1 | tail -3 || true
fi

cat <<EOF

INTERPRET:
  - If step 4 shows "AI Fronter HIT" + EAGI → dialplan OK; live issue is ViciDial not sending customer to ${ROOM}@default
  - If step 4 is empty → fix extensions_custom.conf / extensions.conf _9600XXX GotoIf
  - Try ROOM=9606666 sudo bash test_bot_route.sh if 9600666 fails

LIVE OUTBOUND (during ring, run in 2nd SSH):
  asterisk -rx "core show channels verbose"
  mysql -u custom -pcustom1234 asterisk -e "SELECT channel,status,extension FROM vicidial_auto_calls WHERE campaign_id='testing';"
EOF
