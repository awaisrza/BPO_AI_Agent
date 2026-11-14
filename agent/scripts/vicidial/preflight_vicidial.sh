#!/usr/bin/env bash
# Pre-call check for the ViciDial lab: reload Asterisk config, make sure the
# dialer screens + AudioSocket bridge run, clear stuck calls, free the remote
# agent, and confirm the GPU worker answers. Prints READY only when a dial can work.
#
#   bash preflight_vicidial.sh
#   AGENT=6666 CAMPAIGN=test_cam GPU_HEALTH_URL=http://79.117.116.147:53512/health bash preflight_vicidial.sh
set -uo pipefail

AGENT="${AGENT:-6666}"
CAMPAIGN="${CAMPAIGN:-test_cam}"
PEER="${PEER:-301792431584575}"
GPU_HEALTH_URL="${GPU_HEALTH_URL:-http://79.117.116.147:53512/health}"
FAIL=0

ok()   { echo "  [OK]   $*"; }
bad()  { echo "  [FAIL] $*"; FAIL=1; }
step() { echo; echo "=== $* ==="; }
sql()  { mysql -N -B asterisk -e "$1"; }

step "1. disk + Asterisk"
used=$(df / | tail -1 | awk '{print $5}' | tr -d %)
[ "$used" -lt 90 ] && ok "disk ${used}% used" || bad "disk ${used}% used — truncate /var/log/astguiclient/conf_telnet_log.txt"
if asterisk -rx "core show version" >/dev/null 2>&1; then
  ok "Asterisk running"
else
  bad "Asterisk not running — start it: /usr/share/astguiclient/start_asterisk_boot.pl"
fi
asterisk -rx "sip reload" >/dev/null && asterisk -rx "dialplan reload" >/dev/null && ok "sip + dialplan reloaded"

step "2. SIP trunk + dialplan"
peer=$(asterisk -rx "sip show peer ${PEER}" 2>/dev/null)
echo "$peer" | grep -q "userawaisraza31621719" && ok "trunk user userawaisraza31621719" || bad "trunk peer ${PEER} wrong/missing username"
echo "$peer" | grep -E "^\s*Status" | sed 's/^/  /'
asterisk -rx "dialplan show ${AGENT}@default" | grep -q "ai-fronter-${AGENT}" && ok "${AGENT}@default -> ai-fronter-${AGENT}" || bad "missing [default] exten ${AGENT} Goto(ai-fronter-${AGENT},s,1)"
asterisk -rx "dialplan show s@ai-fronter-${AGENT}" | grep -q "AudioSocket" && ok "AudioSocket step present" || bad "ai-fronter-${AGENT} has no AudioSocket"
asterisk -rx "dialplan show h@ai-fronter-${AGENT}" | grep -q "default,h,1" && ok "hangup handler present (frees agent after call)" || bad "add: exten => h,1,Goto(default,h,1) in [ai-fronter-${AGENT}]"

step "3. dialer background screens"
need_keepalive=0
for s in ASTupdate ASTsend ASTlisten ASTVDauto ASTVDremote; do
  if screen -ls | grep -q "\.${s}\b"; then ok "$s"; else echo "  [MISS] $s"; need_keepalive=1; fi
done
if [ "$need_keepalive" = 1 ]; then
  /usr/share/astguiclient/ADMIN_keepalive_ALL.pl --cu3way >/dev/null 2>&1
  sleep 5
  for s in ASTupdate ASTVDauto ASTVDremote; do
    screen -ls | grep -q "\.${s}\b" && ok "$s started" || bad "$s still missing"
  done
fi

step "4. AudioSocket bridge"
unit="ai-fronter-audiosocket@${AGENT}"
systemctl restart "$unit" 2>/dev/null
sleep 2
systemctl is-active --quiet "$unit" && ok "$unit active (restarted)" || bad "$unit not active: journalctl -u $unit -n 30"
ss -ltn | grep -q ":9092 " && ok "listening on 127.0.0.1:9092" || bad "nothing listening on 9092"

step "5. clear stuck calls + free agent ${AGENT}"
live=$(asterisk -rx "core show channels concise" | grep -c "^SIP/${PEER}" || true)
if [ "$live" -gt 0 ]; then
  bad "${live} live trunk call(s) still up — hang up first (asterisk -rx 'channel request hangup all')"
else
  sql "DELETE FROM vicidial_auto_calls WHERE campaign_id='${CAMPAIGN}';"
  sql "UPDATE vicidial_live_agents SET status='READY', lead_id=0, uniqueid='', callerid='', channel='', comments='' WHERE user='${AGENT}';"
  ok "no live calls; auto_calls cleared"
fi
agent_row=$(sql "SELECT status,campaign_id FROM vicidial_live_agents WHERE user='${AGENT}';")
[ -n "$agent_row" ] && ok "agent ${AGENT}: ${agent_row}" || bad "agent ${AGENT} not logged in (vicidial_remote_agents status ACTIVE?)"
sql "SELECT active,dial_method FROM vicidial_campaigns WHERE campaign_id='${CAMPAIGN}';" | sed 's/^/  campaign active,dial_method: /'
hopper=$(sql "SELECT count(*) FROM vicidial_hopper WHERE campaign_id='${CAMPAIGN}';")
echo "  hopper rows waiting: ${hopper} (each one will be dialed!)"

step "6. GPU worker reachable from ViciDial"
body=$(curl -s --max-time 5 "$GPU_HEALTH_URL" || true)
echo "$body" | grep -q '"ready":true' && ok "GPU ready: $body" || bad "GPU not ready (${body:-no response}) — run preflight_gpu.sh on the GPU"

echo
if [ "$FAIL" = 0 ]; then
  echo "##########  VICIDIAL READY — dial now  ##########"
else
  echo "##########  VICIDIAL NOT READY — fix [FAIL] lines first  ##########"
  exit 1
fi
