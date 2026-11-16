#!/usr/bin/env bash
# Run on the ViciDial server as root when non_agent_api.php times out from the dashboard.
set -euo pipefail

echo "=== ViciDial API repair ($(date -Is)) ==="

echo
echo "--- disk ---"
df -h / /var /var/log 2>/dev/null || df -h

if df / | tail -1 | awk '{print $5}' | grep -qE '^9[0-9]%|^100%'; then
  echo "WARNING: root filesystem nearly full — truncating astguiclient conf_update logs"
  truncate -s 0 /var/log/astguiclient/conf_update.* 2>/dev/null || true
  journalctl --vacuum-size=200M 2>/dev/null || true
fi

echo
echo "--- apache/httpd ---"
if systemctl is-active httpd &>/dev/null; then
  systemctl status httpd --no-pager -l | head -5
elif systemctl is-active apache2 &>/dev/null; then
  systemctl status apache2 --no-pager -l | head -5
else
  echo "Neither httpd nor apache2 is active — starting httpd"
  systemctl start httpd 2>/dev/null || systemctl start apache2
fi

echo
echo "--- local API version (must return in <5s) ---"
if ! curl -m 5 -sf "http://127.0.0.1/vicidial/non_agent_api.php?function=version&source=repair"; then
  echo "Local API failed — restarting web server"
  systemctl restart httpd 2>/dev/null || systemctl restart apache2
  sleep 2
  curl -m 10 -s "http://127.0.0.1/vicidial/non_agent_api.php?function=version&source=repair" || true
fi

echo
echo "--- mysql ---"
M="${MYSQL_CMD:-mysql -u custom -pcustom1234 asterisk}"
$M -e "SELECT 1 AS ok;" 2>/dev/null || {
  echo "MySQL login failed — set MYSQL_CMD or fix credentials"
  exit 1
}

echo "Slow queries / locks:"
$M -e "SHOW FULL PROCESSLIST;" 2>/dev/null | head -25

echo
echo "--- repair tables (safe; may take 1-2 min) ---"
for t in vicidial_hopper vicidial_list vicidial_live_agents vicidial_campaigns; do
  echo "REPAIR TABLE $t"
  $M -e "REPAIR TABLE $t;" 2>/dev/null || true
done

echo
echo "--- dialer processes ---"
pgrep -af 'AST_VDauto_dial|AST_VDremote_agents' || echo "Dialer not running"

if ! pgrep -f AST_VDauto_dial.pl >/dev/null; then
  echo "Starting auto-dialer..."
  /usr/share/astguiclient/ADMIN_restart.pl 2>/dev/null || true
fi

echo
echo "--- port 80 listening ---"
ss -tlnp | grep ':80 ' || netstat -tlnp | grep ':80 ' || echo "Nothing on port 80!"

echo
echo "--- firewall (port 80 must be open to dashboard) ---"
iptables -L INPUT -n 2>/dev/null | head -15 || true

echo
echo "=== Done. Test from your PC: ==="
echo "  curl -m 10 http://$(curl -s ifconfig.me 2>/dev/null || echo '169.58.105.180')/vicidial/non_agent_api.php?function=version&source=test"
