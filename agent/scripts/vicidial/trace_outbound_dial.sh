#!/usr/bin/env bash
# Deep trace: phone not ringing on outbound test dial.
# Usage: bash trace_outbound_dial.sh [campaign] [phone_code] [phone_number]
set -euo pipefail

M="${MYSQL_CMD:-mysql -u custom -pcustom1234 asterisk}"
CAMP="${1:-testing}"
PCODE="${2:-92}"
PNUM="${3:-3142222318}"

echo "=== OUTBOUND TRACE campaign=$CAMP target=+${PCODE}${PNUM} $(date) ==="

echo
echo "=== 1) Dialer processes ==="
pgrep -af 'AST_VDauto_dial|AST_VDremote_agents' || echo "NO DIALER — start: /usr/share/astguiclient/AST_VDauto_dial.pl &"

echo
echo "=== 2) Campaign dial settings ==="
$M -e "
SELECT campaign_id, active, dial_method, auto_dial_level, hopper_level,
       dial_prefix, campaign_cid, cid_group_id, local_call_time,
       lead_filter_id, dial_statuses, drop_lockout_time
FROM vicidial_campaigns WHERE campaign_id='$CAMP'\G"

echo
echo "=== 3) Remote agent + live agent ==="
$M -e "SELECT * FROM vicidial_remote_agents WHERE user_start='6666'\G" 2>/dev/null || true
$M -e "SELECT user, status, campaign_id, lead_id, callerid, channel, last_call_time, outbound_autodial
       FROM vicidial_live_agents WHERE user='6666'\G"

echo
echo "=== 4) Hopper (all statuses) ==="
$M -e "SELECT status, COUNT(*) n FROM vicidial_hopper WHERE campaign_id='$CAMP' GROUP BY status;"
$M -e "
SELECT h.hopper_id, h.lead_id, h.status, h.priority, h.gmt_offset_now,
       l.phone_code, l.phone_number, l.status AS lead_status, l.called_count,
       l.called_since_last_reset, l.list_id
FROM vicidial_hopper h
LEFT JOIN vicidial_list l ON h.lead_id = l.lead_id
WHERE h.campaign_id='$CAMP'
ORDER BY h.hopper_id DESC LIMIT 10;"

echo
echo "=== 5) Target lead in vicidial_list ==="
$M -e "
SELECT lead_id, list_id, status, called_count, called_since_last_reset,
       phone_code, phone_number, gmt_offset_now, entry_date, last_local_call_time
FROM vicidial_list
WHERE phone_code='$PCODE' AND phone_number='$PNUM'
ORDER BY lead_id DESC LIMIT 5;"

echo
echo "=== 6) Recent dial attempts (auto_calls) ==="
$M -e "
SELECT call_time, campaign_id, phone_number, status, stage, lead_id, alt_dial, call_type
FROM vicidial_auto_calls
ORDER BY call_time DESC LIMIT 10;" 2>/dev/null || echo "(table empty or missing columns)"

echo
echo "=== 7) Recent call log ==="
$M -e "
SELECT call_date, phone_number, status, term_reason, length_in_sec, campaign_id, user
FROM vicidial_log
WHERE call_date > DATE_SUB(NOW(), INTERVAL 1 HOUR)
ORDER BY call_date DESC LIMIT 10;" 2>/dev/null || true

echo
echo "=== 8) Carrier / trunk (campaign) ==="
$M -e "
SELECT campaign_id, dial_prefix, campaign_cid, campaign_vdad_exten
FROM vicidial_campaigns WHERE campaign_id='$CAMP';"
$M -e "SELECT carrier_id, carrier_name, registration_string, active FROM vicidial_server_carriers WHERE active='Y' LIMIT 5;" 2>/dev/null || true

echo
echo "=== 9) Asterisk channels (live calls right now) ==="
asterisk -rx "core show channels concise" 2>/dev/null | head -10 || true

echo
echo "=== 10) FORCE: reset lead + inject hopper (bypasses API) ==="
LEAD_ID=$($M -N -e "SELECT lead_id FROM vicidial_list WHERE phone_code='$PCODE' AND phone_number='$PNUM' ORDER BY lead_id DESC LIMIT 1;")
if [ -z "$LEAD_ID" ]; then
  echo "No lead found — create via dashboard Test dial or add_lead API first."
else
  echo "Using lead_id=$LEAD_ID"
  $M -e "
    UPDATE vicidial_list SET
      status='NEW', called_count=0, called_since_last_reset='N',
      user='6666', campaign_id='$CAMP'
    WHERE lead_id='$LEAD_ID';
    DELETE FROM vicidial_hopper WHERE campaign_id='$CAMP';
    INSERT INTO vicidial_hopper (lead_id, campaign_id, status, priority, source)
    VALUES ('$LEAD_ID', '$CAMP', 'READY', 0, 'MANUAL');
  "
  echo "Hopper after inject:"
  $M -e "
    SELECT h.hopper_id, h.status, l.phone_code, l.phone_number
    FROM vicidial_hopper h JOIN vicidial_list l ON h.lead_id=l.lead_id
    WHERE h.campaign_id='$CAMP';"
  echo "Wait 30-60s. Watch: watch -n2 \"mysql -u custom -pcustom1234 asterisk -N -e 'SELECT COUNT(*) FROM vicidial_auto_calls WHERE call_time > NOW()-INTERVAL 2 MINUTE'\""
fi

echo
echo "=== 11) Common fixes ==="
echo "- campaign_cid must be E.164 with + for Telnyx (e.g. +19482194316):"
echo "  UPDATE vicidial_campaigns SET campaign_cid='+19482194316' WHERE campaign_id='$CAMP';"
echo "- If hopper status NEW: UPDATE vicidial_hopper SET status='READY' WHERE campaign_id='$CAMP';"
echo "- If lead maxed: UPDATE vicidial_list SET called_count=0, called_since_last_reset='N' WHERE lead_id=$LEAD_ID;"
