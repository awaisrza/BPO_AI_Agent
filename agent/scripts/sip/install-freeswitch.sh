#!/usr/bin/env bash
# Install FreeSWITCH + mod_audio_stream on Ubuntu 22.04/24.04 (SIP edge VPS).
# Run as root: bash install-freeswitch.sh
set -euo pipefail

FS_DOMAIN="${SIP_EDGE_DOMAIN:-bots.example.com}"
FS_PUBLIC_IP="${SIP_EDGE_PUBLIC_IP:-}"

echo "==> Installing FreeSWITCH dependencies"
apt-get update
apt-get install -y \
  gnupg2 wget lsb-release ca-certificates \
  libevent-dev libspeexdsp-dev libssl-dev zlib1g-dev \
  git cmake build-essential pkg-config

if ! command -v freeswitch >/dev/null 2>&1; then
  echo "==> Adding SignalWire FreeSWITCH repo (Debian/Ubuntu)"
  wget --http-user=signalwire --http-password=patrom -O - \
    https://freeswitch.signalwire.com/repo/deb/debian-release/signalwire-freeswitch-repo.gpg.key \
    | gpg --dearmor -o /usr/share/keyrings/signalwire-freeswitch-repo.gpg 2>/dev/null || true
  if [[ ! -f /usr/share/keyrings/signalwire-freeswitch-repo.gpg ]]; then
    echo "WARN: SignalWire repo key failed — install FreeSWITCH manually or use distro package."
    echo "See: https://developer.signalwire.com/freeswitch/FreeSWITCH-Explained/Installation/"
  else
    echo "deb [signed-by=/usr/share/keyrings/signalwire-freeswitch-repo.gpg] https://freeswitch.signalwire.com/repo/deb/debian-release/ $(lsb_release -sc) main" \
      > /etc/apt/sources.list.d/freeswitch.list
    apt-get update
    apt-get install -y freeswitch-meta-vanilla freeswitch-mod-commands freeswitch-mod-dptools \
      freeswitch-mod-dialplan-xml freeswitch-mod-sofia freeswitch-mod-loopback freeswitch-mod-event-socket
  fi
fi

echo "==> Building mod_audio_stream"
MOD_SRC="${MOD_SRC:-/usr/src/mod_audio_stream}"
if [[ ! -d "$MOD_SRC/.git" ]]; then
  git clone --depth 1 https://github.com/amigniter/mod_audio_stream.git "$MOD_SRC"
  cd "$MOD_SRC"
  git submodule update --init --recursive
else
  cd "$MOD_SRC"
  git pull --ff-only || true
fi

mkdir -p build && cd build
cmake -DCMAKE_BUILD_TYPE=Release ..
make -j"$(nproc)"
make install
ldconfig 2>/dev/null || true

echo "==> Installing AI Fronter dialplan + Lua helper"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
install -d /etc/freeswitch/dialplan/public
install -m 0644 "$REPO_ROOT/scripts/sip/freeswitch/ai_fronter.xml" \
  /etc/freeswitch/dialplan/public/ai_fronter.xml
install -d /etc/freeswitch/scripts
install -m 0755 "$REPO_ROOT/scripts/sip/freeswitch/ai_fronter_stream.lua" \
  /etc/freeswitch/scripts/ai_fronter_stream.lua

if [[ -n "$FS_PUBLIC_IP" ]]; then
  echo "==> Setting external SIP/RTP IP to $FS_PUBLIC_IP"
  sed -i "s/external_sip_ip=.*/external_sip_ip=$FS_PUBLIC_IP/" /etc/freeswitch/vars.xml 2>/dev/null || true
  sed -i "s/external_rtp_ip=.*/external_rtp_ip=$FS_PUBLIC_IP/" /etc/freeswitch/vars.xml 2>/dev/null || true
fi

echo "==> Enabling modules"
grep -q 'mod_audio_stream' /etc/freeswitch/autoload_configs/modules.conf.xml 2>/dev/null || \
  sed -i 's|</modules>|    <load module="mod_audio_stream"/>\n  </modules>|' \
    /etc/freeswitch/autoload_configs/modules.conf.xml || true

systemctl enable freeswitch 2>/dev/null || true
systemctl restart freeswitch 2>/dev/null || service freeswitch restart 2>/dev/null || true

echo "==> Verify"
fs_cli -x "module_exists mod_audio_stream" || true
fs_cli -x "reloadxml" || true

cat <<EOF

Done. Next steps:
  1. Deploy run_sip_edge.py (systemd unit in deploy/sip-edge/)
  2. Point DNS *.${FS_DOMAIN} -> this VPS
  3. Open UDP 5060 + 10000-20000 to BPO dialer IPs
  4. Test: fs_cli -x "originate loopback/6666/default &echo"

EOF
