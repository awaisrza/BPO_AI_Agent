#!/usr/bin/env bash
# Run on ViciDial IMMEDIATELY after a silent dashboard/outbound test call.
#
#   bash capture_after_call.sh

set -euo pipefail

CAMPAIGN="${CAMPAIGN:-testing}"
PHONE="${PHONE:-3142222318}"
MYSQL=(mysql -u custom -pcustom1234 asterisk)

echo "==> 1) Last outbound log row"
"${MYSQL[@]}" -e "
SELECT call_date, status, length_in_sec, term_reason, channel
FROM vicidial_log
WHERE phone_number LIKE '%${PHONE}%'
ORDER BY call_date DESC LIMIT 1;"

echo
echo "==> 2) Last manager originate (shows conf ext + context ViciDial used)"
"${MYSQL[@]}" -e "
SELECT entry_date, status, action, channel, exten, context, cmd_line_b
FROM vicidial_manager
ORDER BY entry_date DESC LIMIT 8;"

echo
echo "==> 3) Conference row for agent 6666"
"${MYSQL[@]}" -e "
SELECT conf_exten, extension, server_ip FROM vicidial_conferences WHERE conf_exten='6666';"

echo
echo "==> 4) Dialplan for both room formats"
asterisk -rx "dialplan show 9600666@default" | head -12
echo "---"
asterisk -rx "dialplan show 9606666@default" | head -8

echo
echo "==> 5) Asterisk log (last 40 lines matching this call)"
grep -iE 'AI Fronter|138368|9600666|9606666|ConfBridge|Local/6666|EAGI|9231|3142222318|TELNYX|VDAD' \
  /var/log/asterisk/messages 2>/dev/null | tail -40 || echo "(no matches)"

echo
echo "==> 6) Bridge log"
tail -15 /var/log/ai-fronter-bridge.log 2>/dev/null || echo "(no bridge log)"

echo
echo "==> 7) Manual routing test (proves dialplan without phone)"
asterisk -rx "channel originate Local/9600666@default/n application Wait 8" &
sleep 2
grep -iE 'AI Fronter HIT|Local/6666|EAGI|bridged to GPU' /var/log/asterisk/messages | tail -5 || true
wait 2>/dev/null || true

cat <<'EOF'

READ:
  138368@default + Wait(2) + Hangup → stock VDAD path (must override to ai-fronter-route)
  "AI Fronter HIT" in step 5 or 7 → dialplan OK
  ConfBridge without HIT → customer still in empty conference
  length_in_sec 1-5 + term_reason CALLER → ViciDial dropped (no agent audio)
EOF
