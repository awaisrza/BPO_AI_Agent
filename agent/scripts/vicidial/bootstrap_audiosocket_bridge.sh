#!/usr/bin/env bash
# Bootstrap AI Fronter AudioSocket bridge on ViciDial (run as root).
#
# One command (set DEPLOY_URL to your GPU file server — see serve_bridge_deploy.sh):
#   curl -fsSL "${DEPLOY_URL}/bootstrap_audiosocket_bridge.sh" | bash
#
# Or copy this script to the dialer and run:
#   bash bootstrap_audiosocket_bridge.sh
#
# Fetch order: BRIDGE_URL → DEPLOY_URL/agi_bridge.py → git repo → /tmp/BPO_AI_Agent pull

set -euo pipefail

AGENT_USER="${AI_FRONTER_AGENT_USER:-6666}"
INSTALL_BIN="/usr/local/bin/ai-fronter-bridge.py"
CONFIG_FILE="${AI_FRONTER_CONFIG:-/etc/ai-fronter/agent_port_map.json}"
LOG_FILE="${AI_FRONTER_LOG:-/var/log/ai-fronter-bridge.log}"
AUDIOSOCKET_HOST="${AI_FRONTER_AUDIOSOCKET_HOST:-127.0.0.1}"
AUDIOSOCKET_PORT="${AI_FRONTER_AUDIOSOCKET_PORT:-9092}"
WORKDIR="${AI_FRONTER_WORKDIR:-/tmp/ai-fronter-bridge-install}"
REPO_URL="${AI_FRONTER_REPO_URL:-https://github.com/awaisrza/BPO_AI_Agent.git}"
REPO_DIR="${AI_FRONTER_REPO_DIR:-/opt/ai-fronter-bridge-src}"
REPO_BRANCH="${AI_FRONTER_REPO_BRANCH:-main}"
BRIDGE_REL="agent/scripts/vicidial/agi_bridge.py"
MIN_LINES="${AI_FRONTER_BRIDGE_MIN_LINES:-900}"
SERVICE_NAME="ai-fronter-audiosocket"

log() { echo "==> $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

need_root() {
  [[ "${EUID:-$(id -u)}" -eq 0 ]] || die "Run as root"
}

read_gpu_host() {
  if [[ -f "$CONFIG_FILE" ]]; then
    python3 - <<'PY' 2>/dev/null || true
import json, os
path = os.environ["CONFIG_FILE"]
try:
    data = json.load(open(path))
    print(data.get("gpu_host", "") or "")
except Exception:
    pass
PY
  fi
}

validate_bridge() {
  local path="$1"
  [[ -s "$path" ]] || return 1
  local lines
  lines="$(wc -l < "$path")"
  [[ "$lines" -ge "$MIN_LINES" ]] || return 1
  grep -q "serve.audiosocket" "$path" || grep -q "serve_audiosocket" "$path" || return 1
  python3 -m py_compile "$path"
  return 0
}

fetch_to() {
  local dest="$1"
  local url="$2"
  log "Downloading $url"
  curl -fsSL --max-time 60 "$url" -o "$dest"
  [[ -s "$dest" ]]
}

try_local_paths() {
  local candidate
  for candidate in \
    "/tmp/BPO_AI_Agent/${BRIDGE_REL}" \
    "${REPO_DIR}/${BRIDGE_REL}" \
    "/tmp/agi_bridge_new.py" \
    "/tmp/agi_bridge.py"; do
    if [[ -f "$candidate" ]] && validate_bridge "$candidate"; then
      log "Using local copy: $candidate"
      /bin/cp -f "$candidate" "$INSTALL_BIN"
      return 0
    fi
  done
  return 1
}

try_git() {
  log "Fetching from git ($REPO_URL)"
  if [[ ! -d "$REPO_DIR/.git" ]]; then
    git clone --depth 1 -b "$REPO_BRANCH" "$REPO_URL" "$REPO_DIR"
  else
    git -C "$REPO_DIR" fetch origin "$REPO_BRANCH" --depth 1
    git -C "$REPO_DIR" checkout -f "$REPO_BRANCH"
    git -C "$REPO_DIR" reset --hard "origin/${REPO_BRANCH}"
  fi
  local src="${REPO_DIR}/${BRIDGE_REL}"
  [[ -f "$src" ]] || die "Missing $src after git clone"
  validate_bridge "$src" || die "Git copy too old (need AudioSocket / --serve-audiosocket)"
  /bin/cp -f "$src" "$INSTALL_BIN"
}

try_deploy_urls() {
  local tmp="${WORKDIR}/agi_bridge.py"
  mkdir -p "$WORKDIR"

  if [[ -n "${BRIDGE_URL:-}" ]]; then
    fetch_to "$tmp" "$BRIDGE_URL"
    validate_bridge "$tmp" || die "BRIDGE_URL file invalid"
    /bin/cp -f "$tmp" "$INSTALL_BIN"
    return 0
  fi

  local gpu_host="${GPU_HOST:-$(CONFIG_FILE=$CONFIG_FILE read_gpu_host)}"
  local base="${DEPLOY_URL:-}"
  if [[ -z "$base" && -n "$gpu_host" && -n "${DEPLOY_PORT:-}" ]]; then
    base="http://${gpu_host}:${DEPLOY_PORT}"
  fi
  if [[ -n "$base" ]]; then
    base="${base%/}"
    if fetch_to "${WORKDIR}/agi_bridge.py.gz.b64" "${base}/agi_bridge.py.gz.b64"; then
      base64 -d "${WORKDIR}/agi_bridge.py.gz.b64" | gzip -d > "$tmp"
      if validate_bridge "$tmp"; then
        /bin/cp -f "$tmp" "$INSTALL_BIN"
        return 0
      fi
    fi
    fetch_to "$tmp" "${base}/agi_bridge.py"
    validate_bridge "$tmp" || die "Deploy URL returned old bridge (no AudioSocket support)"
    /bin/cp -f "$tmp" "$INSTALL_BIN"
    return 0
  fi
  return 1
}

install_deps() {
  if python3 -c "import websocket" 2>/dev/null; then
    log "websocket-client already installed"
  elif command -v pip3 >/dev/null 2>&1; then
    log "Installing websocket-client"
    pip3 install --upgrade websocket-client
  else
    die "pip3 missing — install python3-pip then re-run"
  fi
}

install_bridge_file() {
  chmod 0755 "$INSTALL_BIN"
  local lines size
  lines="$(wc -l < "$INSTALL_BIN")"
  size="$(wc -c < "$INSTALL_BIN")"
  log "Installed $INSTALL_BIN ($lines lines, $size bytes)"
  grep -n "serve.audiosocket" "$INSTALL_BIN" | head -1 || true
}

write_systemd_unit() {
  local unit="/etc/systemd/system/${SERVICE_NAME}.service"
  log "Installing systemd unit $unit"
  cat > "$unit" <<EOF
[Unit]
Description=AI Fronter AudioSocket bridge (agent ${AGENT_USER})
After=network.target asterisk.service

[Service]
Type=simple
Environment=AI_FRONTER_LOG=${LOG_FILE}
Environment=AI_FRONTER_AUDIOSOCKET_HOST=${AUDIOSOCKET_HOST}
Environment=AI_FRONTER_AUDIOSOCKET_PORT=${AUDIOSOCKET_PORT}
ExecStart=/usr/bin/python3 ${INSTALL_BIN} --serve-audiosocket ${AGENT_USER}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable "${SERVICE_NAME}.service"
}

start_service() {
  log "Starting ${SERVICE_NAME}"
  systemctl restart "${SERVICE_NAME}.service"
  sleep 2
  if systemctl is-active --quiet "${SERVICE_NAME}.service"; then
    log "Service active"
  else
    die "Service failed — run: journalctl -u ${SERVICE_NAME} -n 30 --no-pager"
  fi
}

verify_listening() {
  if ss -tlnp | grep -q ":${AUDIOSOCKET_PORT} "; then
    log "AudioSocket listening on ${AUDIOSOCKET_HOST}:${AUDIOSOCKET_PORT}"
    ss -tlnp | grep ":${AUDIOSOCKET_PORT} " || true
  else
    die "Port ${AUDIOSOCKET_PORT} not listening"
  fi
}

check_gpu() {
  local gpu_host port
  gpu_host="$(CONFIG_FILE=$CONFIG_FILE read_gpu_host || true)"
  if [[ -z "$gpu_host" || ! -f "$CONFIG_FILE" ]]; then
    log "Skip GPU health (no $CONFIG_FILE)"
    return 0
  fi
  port="$(python3 - <<PY
import json
m = json.load(open("$CONFIG_FILE"))
agents = m.get("agents") or {}
print(agents.get("$AGENT_USER") or m.get("$AGENT_USER") or "")
PY
)"
  if [[ -n "$port" ]]; then
    log "GPU health http://${gpu_host}:${port}/health"
    curl -s --max-time 5 "http://${gpu_host}:${port}/health" || echo "  (health check failed)"
  fi
}

hopper_ready() {
  if [[ "${SKIP_HOPPER:-}" == "1" ]]; then
    return 0
  fi
  local campaign="${CAMPAIGN_ID:-testing}"
  if command -v mysql >/dev/null 2>&1; then
    log "Setting hopper READY for campaign ${campaign}"
    mysql asterisk -e \
      "UPDATE vicidial_hopper SET status='READY' WHERE campaign_id='${campaign}';" \
      2>/dev/null || log "Hopper update skipped (mysql creds?)"
  fi
}

main() {
  need_root
  log "AI Fronter AudioSocket bootstrap (agent ${AGENT_USER})"

  if try_deploy_urls; then
    log "Bridge source: URL"
  elif try_local_paths; then
    log "Bridge source: local file"
  elif try_git; then
    log "Bridge source: git"
  else
    cat >&2 <<EOF

Could not find a valid bridge (need >=${MIN_LINES} lines + --serve-audiosocket).

Options:
  1) GPU deploy server (recommended):
       On GPU:  bash serve_bridge_deploy.sh
       On dialer: DEPLOY_URL=http://GPU_IP:PORT bash bootstrap_audiosocket_bridge.sh

  2) Direct URL:
       BRIDGE_URL=http://GPU_IP:PORT/agi_bridge.py bash bootstrap_audiosocket_bridge.sh

  3) Git (needs outbound HTTPS):
       AI_FRONTER_REPO_URL=https://github.com/you/BPO_AI_Agent.git bash bootstrap_audiosocket_bridge.sh

EOF
    die "No bridge source available"
  fi

  install_deps
  install_bridge_file
  write_systemd_unit
  start_service
  verify_listening
  check_gpu
  hopper_ready

  cat <<EOF

Done.
  Service:  systemctl status ${SERVICE_NAME}
  Logs:     tail -f ${LOG_FILE}
  Test dial from dashboard (do not run test-ws first).

EOF
}

main "$@"
