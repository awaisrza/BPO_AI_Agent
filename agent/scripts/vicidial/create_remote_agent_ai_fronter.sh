#!/usr/bin/env bash
# Create ViciDial user + remote agent for AI Fronter AudioSocket lab (agent 6666 / campaign testing).
# Run on the ViciDial server as root (MobaXterm SSH):
#   bash create_remote_agent_ai_fronter.sh
# Optional env:
#   AGENT=6666 CAMPAIGN=testing CONF_EXTEN=6666 LINES=1
set -euo pipefail

AGENT="${AGENT:-6666}"
CAMPAIGN="${CAMPAIGN:-testing}"
LINES="${LINES:-1}"
CONF_EXTEN="${CONF_EXTEN:-6666}"
CONTEXT="ai-fronter-${AGENT}"

CONF="/etc/astguiclient.conf"
if [[ ! -f "$CONF" ]]; then
  echo "ERROR: $CONF not found — not a ViciDial server?" >&2
  exit 1
fi

read_cfg() {
  local key="$1"
  grep -E "^${key}\s*=>" "$CONF" | head -1 | sed -E "s/^[^=]+=>\s*//" | tr -d ' '
}

DB="${VARDB_database:-$(read_cfg VARDB_database)}"
DB="${DB:-asterisk}"
DB_USER="${VARDB_user:-$(read_cfg VARDB_user)}"
DB_PASS="${VARDB_pass:-$(read_cfg VARDB_pass)}"

if [[ -z "$DB_USER" || -z "$DB_PASS" ]]; then
  echo "ERROR: Could not read VARDB_user / VARDB_pass from $CONF" >&2
  exit 1
fi

MYSQL=(mysql -N -u"$DB_USER" -p"$DB_PASS" "$DB")
MYSQLV=(mysql -u"$DB_USER" -p"$DB_PASS" "$DB")

echo "=== AI Fronter remote agent setup ==="
echo "    agent=$AGENT campaign=$CAMPAIGN lines=$LINES conf_exten=$CONF_EXTEN"
echo "    database=$DB user=$DB_USER"
echo

SERVER_IP="$("${MYSQL[@]}" -e "SELECT server_ip FROM servers WHERE active='Y' ORDER BY server_id LIMIT 1;" 2>/dev/null | head -1 || true)"
if [[ -z "$SERVER_IP" ]]; then
  SERVER_IP="$("${MYSQL[@]}" -e "SELECT server_ip FROM servers ORDER BY server_id LIMIT 1;" | head -1 || true)"
fi
if [[ -z "$SERVER_IP" ]]; then
  echo "ERROR: No row in servers table — set SERVER_IP env and re-run." >&2
  exit 1
fi
echo "Using server_ip=$SERVER_IP"

CAMP_ACTIVE="$("${MYSQL[@]}" -e "SELECT active FROM vicidial_campaigns WHERE campaign_id='${CAMPAIGN}';" | head -1 || true)"
if [[ "$CAMP_ACTIVE" != "Y" ]]; then
  echo "WARNING: campaign '${CAMPAIGN}' missing or not active (active=${CAMP_ACTIVE:-none})"
fi

USER_EXISTS="$("${MYSQL[@]}" -e "SELECT COUNT(*) FROM vicidial_users WHERE user='${AGENT}';" | head -1)"
if [[ "$USER_EXISTS" == "0" ]]; then
  echo "Creating vicidial_users row user=${AGENT} ..."
  "${MYSQLV[@]}" -e "
    INSERT INTO vicidial_users (user, pass, full_name, user_level, active)
    VALUES ('${AGENT}', '${AGENT}', 'AI Fronter Bot', 1, 'Y');
  "
else
  echo "vicidial_users user=${AGENT} already exists — OK"
  "${MYSQLV[@]}" -e "UPDATE vicidial_users SET active='Y' WHERE user='${AGENT}';" 2>/dev/null || true
fi

CA_EXISTS="$("${MYSQL[@]}" -e "SELECT COUNT(*) FROM vicidial_campaign_agents WHERE user='${AGENT}' AND campaign_id='${CAMPAIGN}';" | head -1)"
if [[ "$CA_EXISTS" == "0" ]]; then
  echo "Linking user ${AGENT} to campaign ${CAMPAIGN} ..."
  "${MYSQLV[@]}" -e "
    INSERT INTO vicidial_campaign_agents (user, campaign_id, campaign_rank, campaign_weight)
    VALUES ('${AGENT}', '${CAMPAIGN}', 0, 0);
  "
else
  echo "vicidial_campaign_agents already linked — OK"
fi

RA_EXISTS="$("${MYSQL[@]}" -e "SELECT COUNT(*) FROM vicidial_remote_agents WHERE user_start='${AGENT}';" | head -1)"
if [[ "$RA_EXISTS" == "0" ]]; then
  echo "Inserting vicidial_remote_agents ..."
  "${MYSQLV[@]}" -e "
    INSERT INTO vicidial_remote_agents
      (user_start, number_of_lines, server_ip, conf_exten, status, campaign_id, extension_group, extension_group_order)
    VALUES
      ('${AGENT}', ${LINES}, '${SERVER_IP}', '${CONF_EXTEN}', 'ACTIVE', '${CAMPAIGN}', 'NONE', 'NONE');
  "
else
  echo "Updating existing vicidial_remote_agents user_start=${AGENT} ..."
  "${MYSQLV[@]}" -e "
    UPDATE vicidial_remote_agents SET
      number_of_lines=${LINES},
      server_ip='${SERVER_IP}',
      conf_exten='${CONF_EXTEN}',
      status='ACTIVE',
      campaign_id='${CAMPAIGN}',
      extension_group='NONE',
      extension_group_order='NONE'
    WHERE user_start='${AGENT}';
  "
fi

CUSTOM="/etc/asterisk/extensions_custom.conf"
INCLUDE_LINE="#include extensions_custom.conf"
EXTCONF="/etc/asterisk/extensions.conf"

ensure_dialplan() {
  local marker="; AI Fronter remote agent ${AGENT}"
  if [[ -f "$CUSTOM" ]] && grep -qF "$marker" "$CUSTOM" 2>/dev/null; then
    echo "Dialplan markers already present in $CUSTOM"
  else
    echo "Appending AudioSocket dialplan to $CUSTOM ..."
    cat >>"$CUSTOM" <<EOF

${marker}
[${CONTEXT}]
exten => s,1,NoOp(AI Fronter AudioSocket agent ${AGENT})
 same => n,Answer()
; Stock Asterisk has no UUID() function; AudioSocket rejects an empty id
 same => n,Set(AS_UUID=\${FILTER(0-9a-f-,\${SHELL(cat /proc/sys/kernel/random/uuid)})})
 same => n,AudioSocket(\${AS_UUID},127.0.0.1:9092)
 same => n,Hangup()
; ViciDial's call_log AGI in default,h clears vicidial_auto_calls and frees the remote agent
exten => h,1,Goto(default,h,1)

; Route remote-agent external extension -> AudioSocket context
; ViciDial sends answered calls to Goto(default,<conf_exten>,1)
[default]
exten => ${AGENT},1,Goto(${CONTEXT},s,1)
EOF
  fi
  if [[ -f "$EXTCONF" ]] && ! grep -qF "$INCLUDE_LINE" "$EXTCONF" 2>/dev/null; then
    echo "Adding $INCLUDE_LINE to $EXTCONF ..."
    echo "$INCLUDE_LINE" >>"$EXTCONF"
  fi
  asterisk -rx "dialplan reload" >/dev/null
  echo "Dialplan context [${CONTEXT}] and exten ${AGENT} -> Goto OK"
}

ensure_dialplan

echo
echo "--- vicidial_remote_agents ---"
"${MYSQLV[@]}" -e "SELECT * FROM vicidial_remote_agents WHERE user_start='${AGENT}'\G"

echo
echo "--- Checks ---"
pgrep -af AST_VDremote_agents >/dev/null && echo "AST_VDremote_agents.pl: running" || echo "WARNING: AST_VDremote_agents.pl not running — run ADMIN_restart.pl"
systemctl is-active --quiet "ai-fronter-audiosocket@${AGENT}" 2>/dev/null && \
  echo "ai-fronter-audiosocket@${AGENT}: active" || \
  echo "NOTE: start bridge: systemctl enable --now ai-fronter-audiosocket@${AGENT}"

echo
echo "Done. Dashboard: Run campaign '${CAMPAIGN}'. Test:"
echo "  tail -f /var/log/ai-fronter-bridge.log"
echo "  asterisk -rx \"channel originate Local/${AGENT}@default application Wait 45\""
