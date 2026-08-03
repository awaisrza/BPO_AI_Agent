#!/usr/bin/env bash
# AI Fronter — one-shot ViciDial test dial setup (run on the dialer server via SSH / MobaXterm).
#
# What it does:
#   1. Activates campaign + sets outbound caller ID
#   2. Activates remote agent 6666
#   3. Adds your test lead to hopper
#   4. Checks GPU worker health
#
# Usage:
#   sudo bash run_test_dial.sh
#   # edit CONFIG below first

set -euo pipefail

# ── CONFIG (edit these) ──────────────────────────────────────────────────────
VD_URL="${VD_URL:-http://127.0.0.1}"          # ViciDial base URL (on-server use 127.0.0.1)
VD_API_USER="${VD_API_USER:-6666}"
VD_API_PASS="${VD_API_PASS:-1234}"

CAMPAIGN_ID="${CAMPAIGN_ID:-testing}"         # must match dashboard vicidial_campaign_id
REMOTE_AGENT_USER="${REMOTE_AGENT_USER:-6666}" # vicidial_agent_user / remote agent login
LIST_ID="${LIST_ID:-}"                        # leave blank to auto-detect from MySQL

OUTBOUND_CID="${OUTBOUND_CID:-+19482194316}"  # E.164 with + (Telnyx requires + on From)
PHONE_CODE="${PHONE_CODE:-92}"                # Pakistan
PHONE_NUMBER="${PHONE_NUMBER:-3142222318}"    # without + or country code

GPU_HOST="${GPU_HOST:-79.101.153.232}"
GPU_WORKER_PORT="${GPU_WORKER_PORT:-16396}"   # public port → worker 10200

LEAD_FIRST_NAME="${LEAD_FIRST_NAME:-Test}"
LEAD_LAST_NAME="${LEAD_LAST_NAME:-Lead}"
# ─────────────────────────────────────────────────────────────────────────────

API="${VD_URL%/}/vicidial/non_agent_api.php"

vd_api() {
  local qs="source=ai-fronter&user=${VD_API_USER}&pass=${VD_API_PASS}&$*"
  curl -sS --max-time 30 "${API}?${qs}" | tr -d '\r'
}

echo "==> 1) API version"
vd_api "function=version" || true
echo

echo "==> 2) Auto-detect list_id for campaign ${CAMPAIGN_ID} (MySQL)"
if [[ -z "${LIST_ID}" ]]; then
  MYSQL_CONF=""
  for f in /etc/astguiclient.conf /usr/share/astguiclient/ADMIN_settings.txt; do
    [[ -f "$f" ]] && MYSQL_CONF="$f" && break
  done
  if [[ -n "$MYSQL_CONF" ]]; then
    # shellcheck disable=SC1090
    source "$MYSQL_CONF" 2>/dev/null || true
  fi
  DB="${VARDB_database:-asterisk}"
  MU="${VARDB_custom_user:-${VARDB_user:-root}}"
  MP="${VARDB_custom_pass:-${VARDB_pass:-}}"
  LIST_ID="$(mysql -N -u"$MU" -p"$MP" "$DB" -e \
    "SELECT list_id FROM vicidial_lists WHERE campaign_id='${CAMPAIGN_ID}' AND active='Y' ORDER BY list_id LIMIT 1;" \
    2>/dev/null || true)"
fi
if [[ -z "${LIST_ID}" ]]; then
  echo "ERROR: Could not detect list_id. Set LIST_ID manually, e.g.:"
  echo "  export LIST_ID=101"
  echo "  sudo -E bash $0"
  exit 1
fi
echo "    list_id=${LIST_ID}"
echo

echo "==> 3) Activate campaign (caller ID: set campaign_cid='+19482194316' in Admin/SQL — API strips +)"
RESP="$(vd_api \
  "function=update_campaign" \
  "campaign_id=${CAMPAIGN_ID}" \
  "active=Y" \
  "auto_dial_level=1" \
  "dial_method=RATIO" \
  "reset_hopper=Y" \
  "hopper_level=100")"
echo "$RESP"
echo "$RESP" | grep -qE 'SUCCESS|NOTICE' || {
  echo "WARN: update_campaign may have failed — check API user level 8+ and modify campaigns permission"
}
echo

echo "==> 4) Activate remote agent ${REMOTE_AGENT_USER}"
RESP="$(vd_api \
  "function=update_remote_agent" \
  "agent_user=${REMOTE_AGENT_USER}" \
  "status=ACTIVE" \
  "campaign_id=${CAMPAIGN_ID}" \
  "number_of_lines=1")"
echo "$RESP"
echo

echo "==> 5) Add lead +${PHONE_CODE}${PHONE_NUMBER} to hopper"
RESP="$(vd_api \
  "function=add_lead" \
  "phone_number=${PHONE_NUMBER}" \
  "phone_code=${PHONE_CODE}" \
  "list_id=${LIST_ID}" \
  "first_name=${LEAD_FIRST_NAME}" \
  "last_name=${LEAD_LAST_NAME}" \
  "add_to_hopper=Y" \
  "hopper_local_call_time_check=N" \
  "dnc_check=N" \
  "campaign_dnc_check=N")"
echo "$RESP"
echo

echo "==> 5b) Set hopper READY (auto-dialer ignores NEW)"
mysql -u"${MYSQL_USER:-custom}" -p"${MYSQL_PASS:-custom1234}" "${DB:-asterisk}" -e "
UPDATE vicidial_hopper SET status='READY'
WHERE campaign_id='${CAMPAIGN_ID}' AND status IN ('NEW','','RH');" 2>/dev/null || true
echo
vd_api "function=hopper_list" "campaign_id=${CAMPAIGN_ID}" "stage=csv" | head -20
echo

echo "==> 7) GPU worker health"
curl -sS --max-time 10 "http://${GPU_HOST}:${GPU_WORKER_PORT}/health" || echo "GPU worker not reachable"
echo

echo "==> 8) Live channels (should show outbound dial shortly)"
asterisk -rx "core show channels" 2>/dev/null || true
echo

cat <<EOF

DONE — next steps:
  1. On GPU: supervisor + worker running (curl http://127.0.0.1:8770/status)
  2. Dashboard: click Run on the campaign (starts GPU sync)
  3. Wait 30–60s — ViciDial auto-dialer should call +${PHONE_CODE}${PHONE_NUMBER}
  4. Watch logs:
       GPU:      tail -f /tmp/vicidial_events.log
       ViciDial: tail -f /var/log/asterisk/full | grep -iE '6666|fronter|EAGI'

If no dial: check trunk supports +${PHONE_CODE} and campaign is ACTIVE.
EOF
