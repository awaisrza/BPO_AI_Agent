#!/usr/bin/env bash
# Why is the phone not ringing? Run on ViciDial as root.
set -euo pipefail

M="${MYSQL_CMD:-mysql -u custom -pcustom1234 asterisk}"
CAMP="${1:-testing}"
AGENT="${2:-6666}"
PHONE="${3:-923142222318}"
PCODE="${4:-92}"

echo "=== Dial diagnostic campaign=$CAMP agent=$AGENT ==="
echo

echo "--- dialer processes (must see auto_dial + remote_agents) ---"
pgrep -af 'AST_VDauto_dial|AST_VDremote_agents|AST_manager' || echo "MISSING — run ADMIN_restart.pl"

echo
echo "--- campaign ---"
$M -N -e "SELECT campaign_id, active, dial_method, auto_dial_level, hopper_level, lead_order FROM vicidial_campaigns WHERE campaign_id='$CAMP';"

echo
echo "--- remote agent $AGENT ---"
$M -N -e "SELECT user_start, number_of_lines, status, campaign_id FROM vicidial_remote_agents WHERE user_start='$AGENT';" 2>/dev/null || \
$M -N -e "SELECT user_start, number_of_lines, campaign_id FROM vicidial_remote_agents WHERE user_start='$AGENT';"

echo
echo "--- live agent ---"
$M -e "SELECT user, status, campaign_id, lead_id, uniqueid, last_call_time FROM vicidial_live_agents WHERE user='$AGENT';"

echo
echo "--- hopper ($CAMP) ---"
$M -e "SELECT status, COUNT(*) n FROM vicidial_hopper WHERE campaign_id='$CAMP' GROUP BY status;"
$M -e "SELECT h.hopper_id, h.lead_id, h.status, l.phone_code, l.phone_number FROM vicidial_hopper h LEFT JOIN vicidial_list l ON h.lead_id=l.lead_id WHERE h.campaign_id='$CAMP' ORDER BY h.hopper_id DESC LIMIT 5;"

echo
echo "--- recent auto calls ---"
$M -e "SELECT call_time, phone_number, status, term_reason FROM vicidial_auto_calls ORDER BY call_time DESC LIMIT 5;" 2>/dev/null || \
$M -e "SELECT call_time, phone_number, status FROM vicidial_auto_calls ORDER BY call_time DESC LIMIT 5;" 2>/dev/null || echo "(no auto_calls table rows)"

echo
echo "--- fix hopper NEW -> READY ---"
$M -e "UPDATE vicidial_hopper SET status='READY' WHERE campaign_id='$CAMP' AND status='NEW'; SELECT ROW_COUNT() AS fixed;"

echo
echo "--- restart dialer if processes missing ---"
if ! pgrep -f AST_VDauto_dial.pl >/dev/null; then
  echo "Starting dialer..."
  /usr/share/astguiclient/ADMIN_restart.pl
  sleep 5
  pgrep -af 'AST_VDauto_dial|AST_VDremote_agents' || true
fi

echo
echo "--- optional: inject test lead (API user/pass from env or edit below) ---"
API_USER="${VICIDIAL_API_USER:-6666}"
API_PASS="${VICIDIAL_API_PASS:-}"
LIST_ID="${LIST_ID:-101}"
if [ -n "$API_PASS" ]; then
  curl -m 15 -s "http://127.0.0.1/vicidial/non_agent_api.php?source=diag&user=${API_USER}&pass=${API_PASS}&function=add_lead&phone_number=${PHONE}&phone_code=${PCODE}&list_id=${LIST_ID}&first_name=Test&last_name=Dial&add_to_hopper=Y&hopper_local_call_time_check=N&dnc_check=N&campaign_dnc_check=N&campaign_id=${CAMP}"
  echo
  $M -e "SELECT h.hopper_id, h.status, l.phone_code, l.phone_number FROM vicidial_hopper h LEFT JOIN vicidial_list l ON h.lead_id=l.lead_id WHERE h.campaign_id='$CAMP' ORDER BY h.hopper_id DESC LIMIT 3;"
else
  echo "Set VICIDIAL_API_PASS to auto-add lead, or use dashboard Test dial."
fi

echo
echo "=== Watch live: tail -f /var/log/astguiclient/auto_dial.log (if exists) ==="
