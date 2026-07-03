"""Patch browser_call_server.py with TURN relays for Vast/NAT WebRTC audio.

Run on the GPU host:
  python scripts/patch_browser_turn.py
"""

from __future__ import annotations

from pathlib import Path

TARGET = Path(__file__).resolve().parent.parent / "app" / "browser_call_server.py"

TURN_BLOCK = '''
# Public TURN relay — HTTP tunnels only carry signaling; audio needs TURN on NAT hosts.
_DEFAULT_ICE_SERVERS_JS = """[
  { urls: "stun:stun.l.google.com:19302" },
  {
    urls: [
      "turn:openrelay.metered.ca:80",
      "turn:openrelay.metered.ca:443",
      "turn:openrelay.metered.ca:443?transport=tcp"
    ],
    username: "openrelayproject",
    credential: "openrelayproject"
  }
]"""


def _server_ice_servers():
    from pipecat.transports.smallwebrtc.connection import IceServer

    return [
        IceServer(urls="stun:stun.l.google.com:19302"),
        IceServer(
            urls=[
                "turn:openrelay.metered.ca:80",
                "turn:openrelay.metered.ca:443",
                "turn:openrelay.metered.ca:443?transport=tcp",
            ],
            username="openrelayproject",
            credential="openrelayproject",
        ),
    ]


'''

OLD_HANDLER = "webrtc_handler = SmallWebRTCRequestHandler()"
NEW_HANDLER = "webrtc_handler = SmallWebRTCRequestHandler(ice_servers=_server_ice_servers())"

OLD_PC = 'iceServers: [{ urls: "stun:stun.l.google.com:19302" }]'
NEW_PC = "iceServers: ICE_SERVERS"

OLD_ICE_SERVERS_PLACEHOLDER = "const ICE_SERVERS = __ICE_SERVERS__;"
ONTRACK_OLD = """      pc.ontrack = (event) => {
        remoteEl.srcObject = event.streams[0];
      };"""
ONTRACK_NEW = """      pc.ontrack = (event) => {
        remoteEl.srcObject = event.streams[0];
        remoteEl.play().catch((err) => console.warn("autoplay:", err));
      };"""


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"Missing {TARGET}")

    text = TARGET.read_text(encoding="utf-8")
    if "_server_ice_servers" in text and "openrelay.metered.ca" in text:
        print("TURN patch already applied.")
        return

    if "from .config import ScriptConfig, settings" in text:
        text = text.replace(
            "from .config import ScriptConfig, settings\n",
            "from .config import ScriptConfig, settings\n" + TURN_BLOCK,
            1,
        )
    else:
        raise SystemExit("Unexpected browser_call_server.py layout — update manually.")

    if OLD_HANDLER in text:
        text = text.replace(OLD_HANDLER, NEW_HANDLER, 1)
    elif NEW_HANDLER not in text:
        raise SystemExit("Could not find SmallWebRTCRequestHandler() line.")

    if OLD_PC in text:
        text = text.replace(OLD_PC, NEW_PC, 1)
        if OLD_ICE_SERVERS_PLACEHOLDER not in text:
            text = text.replace(
                "  <script>\n    let pc = null;",
                "  <script>\n    const ICE_SERVERS = __ICE_SERVERS__;\n    let pc = null;",
                1,
            )
        if '""".replace("__ICE_SERVERS__"' not in text:
            text = text.replace(
                '</html>\n"""',
                '</html>\n""".replace("__ICE_SERVERS__", _DEFAULT_ICE_SERVERS_JS)',
                1,
            )

    if ONTRACK_OLD in text:
        text = text.replace(ONTRACK_OLD, ONTRACK_NEW, 1)

    TARGET.write_text(text, encoding="utf-8")
    print(f"Patched {TARGET}")
    print("Restart: python -m app.main --browser --campaign-id ...")


if __name__ == "__main__":
    main()
