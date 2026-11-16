#!/usr/bin/env bash
# Safe emergency cleanup when ViciDial disk is full.
# Does NOT touch MySQL data, recordings, or /etc/astguiclient.conf
set -euo pipefail

echo "=== Before ==="
df -h / /var /var/log 2>/dev/null || df -h

echo
echo "--- largest under /var/log (top 15) ---"
du -xh /var/log 2>/dev/null | sort -hr | head -15

echo
echo "--- truncating astguiclient conf_update spam (safe) ---"
count=0
for f in /var/log/astguiclient/conf_update.*; do
  [ -f "$f" ] || continue
  size=$(stat -c%s "$f" 2>/dev/null || echo 0)
  if [ "$size" -gt 1048576 ]; then
    echo "  truncate $(numfmt --to=iec "$size" 2>/dev/null || echo "${size}B") $f"
    truncate -s 0 "$f"
    count=$((count + 1))
  fi
done
echo "  truncated $count file(s)"

echo
echo "--- vacuum systemd journal ---"
journalctl --vacuum-size=200M 2>/dev/null || true

echo
echo "--- old rotated logs (>14 days) ---"
find /var/log -type f \( -name '*.gz' -o -name '*.1' -o -name '*.old' \) -mtime +14 -print -delete 2>/dev/null | head -20

echo
echo "--- apache/httpd error logs if huge ---"
for f in /var/log/httpd/error_log /var/log/apache2/error.log; do
  [ -f "$f" ] || continue
  size=$(stat -c%s "$f" 2>/dev/null || echo 0)
  if [ "$size" -gt 524288000 ]; then
    echo "  truncate $f ($(numfmt --to=iec "$size" 2>/dev/null || echo ${size}))"
    truncate -s 0 "$f"
  fi
done

echo
echo "--- restart web + mysql if disk was critical ---"
pct=$(df / | tail -1 | awk '{print $5}' | tr -d '%')
if [ "$pct" -ge 95 ]; then
  echo "  still ${pct}% — restart services"
  systemctl restart mariadb 2>/dev/null || systemctl restart mysql 2>/dev/null || true
  systemctl restart httpd 2>/dev/null || systemctl restart apache2 2>/dev/null || true
fi

echo
echo "=== After ==="
df -h /

echo
echo "--- API smoke test ---"
curl -m 5 -s "http://127.0.0.1/vicidial/non_agent_api.php?function=version&source=cleanup" && echo || echo "API still failing — run repair_vicidial_api.sh"

echo
echo "=== Prevent repeat: add weekly cron (optional) ==="
echo '0 3 * * 0 root truncate -s 0 /var/log/astguiclient/conf_update.* 2>/dev/null; journalctl --vacuum-size=200M'
