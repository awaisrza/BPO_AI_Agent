#!/usr/bin/env bash
# Run ON the ViciDial/Asterisk server when hopper has leads but the phone never rings.
#
#   sudo bash diagnose_and_fix_dial.sh
#
# Edit CONFIG if needed:

set -euo pipefail

CAMPAIGN_ID="${CAMPAIGN_ID:-testing}"
REMOTE_AGENT="${REMOTE_AGENT:-6666}"
DB="${DB:-asterisk}"
MYSQL_USER="${MYSQL_USER:-custom}"
MYSQL_PASS="${MYSQL_PASS:-custom1234}"

mysql_q() {
  mysql -N -u"$MYSQL_USER" -p"$MYSQL_PASS" "$DB" -e "$1" 2>/dev/null
}

echo "==> 1) Campaign ${CAMPAIGN_ID}"
mysql_q "
SELECT CONCAT('active=', active, ' dial_method=', dial_method, ' level=', auto_dial_level,
              ' hopper_level=', hopper_level, ' cid=', campaign_cid)
FROM vicidial_campaigns WHERE campaign_id='${CAMPAIGN_ID}';" || echo "  (could not query — check MySQL creds)"
echo

echo "==> 2) Remote agent ${REMOTE_AGENT}"
mysql_q "
SELECT CONCAT('status=', status, ' campaign=', campaign_id, ' lines=', number_of_lines,
              ' conf_exten=', conf_exten)
FROM vicidial_remote_agents WHERE user_start='${REMOTE_AGENT}';" || true
echo

echo "==> 3) Hopper (auto-dialer only picks status=READY, not NEW)"
mysql_q "
SELECT h.lead_id, l.phone_code, l.phone_number, h.status
FROM vicidial_hopper h
JOIN vicidial_list l ON h.lead_id=l.lead_id
WHERE h.campaign_id='${CAMPAIGN_ID}';" || true
echo

echo "==> 3b) Clear stuck dials + set hopper READY"
mysql -u"$MYSQL_USER" -p"$MYSQL_PASS" "$DB" -e "
DELETE FROM vicidial_auto_calls WHERE campaign_id='${CAMPAIGN_ID}';
DELETE FROM vicidial_manager WHERE status IN ('NEW','QUEUE','SENT');
UPDATE vicidial_hopper SET status='READY'
WHERE campaign_id='${CAMPAIGN_ID}' AND status IN ('NEW','','RH');
UPDATE vicidial_live_agents
SET status='READY', lead_id=0, uniqueid='', channel=''
WHERE user='${REMOTE_AGENT}';" 2>/dev/null || true
mysql_q "
SELECT CONCAT('hopper lead ', lead_id, ' status=', status)
FROM vicidial_hopper WHERE campaign_id='${CAMPAIGN_ID}' LIMIT 3;" || true
echo

echo "==> 4) Auto-dialer process"
if ps aux | grep -iE 'AST_VDauto|VDauto_dial' | grep -v grep; then
  echo "  auto-dialer: RUNNING"
else
  echo "  auto-dialer: NOT RUNNING — start campaign in ViciDial Admin or run AST_VDauto_dial.pl"
fi
echo

echo "==> 5) Active Asterisk channels"
asterisk -rx "core show channels concise" 2>/dev/null | head -5 || true
echo

echo "==> 6) Fix remote agent if INACTIVE (safe to re-run)"
mysql -u"$MYSQL_USER" -p"$MYSQL_PASS" "$DB" -e "
UPDATE vicidial_remote_agents
SET status='ACTIVE', campaign_id='${CAMPAIGN_ID}', number_of_lines=1, conf_exten='${REMOTE_AGENT}'
WHERE user_start='${REMOTE_AGENT}';" 2>/dev/null || true

mysql_q "
SELECT CONCAT('after fix: status=', status, ' campaign=', campaign_id)
FROM vicidial_remote_agents WHERE user_start='${REMOTE_AGENT}';" || true
echo

echo "==> 7) GPU bridge test (needs websocket-client + /etc/ai-fronter config)"
if [[ -x /usr/local/bin/ai-fronter-bridge.py ]]; then
  /usr/local/bin/ai-fronter-bridge.py --test-ws "${REMOTE_AGENT}" 2>&1 | tail -3 || true
else
  echo "  ai-fronter-bridge.py not installed"
fi
echo

echo "==> 8) Recent dial attempts (watch for 9231 / CONGESTION / CHANUNAVAIL)"
grep -iE '9231|6666|Dial|CONGESTION|CHANUNAVAIL|hopper' /var/log/asterisk/messages 2>/dev/null | tail -15 || \
  echo "  no matching lines in messages log"
echo

cat <<EOF
NEXT:
  - Hopper status must be READY (add_lead API sets NEW — script step 3b fixes it)
  - If auto-dialer NOT RUNNING: ViciDial Admin → Campaign ${CAMPAIGN_ID} → set Active=Y
  - If remote agent INACTIVE: re-run this script or fix in Admin → Remote Agents
  - If trunk errors (CONGESTION): outbound route may not support +92 Pakistan
  - Dashboard + GPU are ready — this script is the remaining piece
EOF
