#!/usr/bin/env python3
"""ViciDial EAGI audio bridge — forwards call audio to AI Fronter GPU workers.

Runs on the BPO Asterisk/ViciDial server. Invoked from dialplan as EAGI:

    EAGI(/usr/local/bin/ai-fronter-bridge.py,6666)

The script opens a WebSocket to the GPU fleet worker and speaks Telnyx Media
Streams JSON (PCMU @ 8 kHz), matching agent/app/vicidial_session.py.

Configuration (first match wins for media port):
  1. CLI arg: vicidial agent user (e.g. 6666)
  2. AI_FRONTER_MEDIA_PORT — fixed port override
  3. /etc/ai-fronter/agent_port_map.json — static agent → port map
  4. GPU supervisor GET /status — live vicidial_agent_user → media_port

Environment:
  AI_FRONTER_GPU_HOST       GPU public IP (default: from config or 127.0.0.1)
  AI_FRONTER_CONFIG         Path to agent_port_map.json
  AI_FRONTER_EAGI_FORMAT    slin (default) — Asterisk EAGI fd 3 is always slin
  AI_FRONTER_LOG            Log file path (optional)
  AI_FRONTER_WS_TIMEOUT     WebSocket connect timeout seconds (default 8)

Dependencies on dialer server:
  pip install websocket-client

Test without Asterisk:
  python3 ai-fronter-bridge.py --test-ws 6666
"""

from __future__ import annotations

import argparse
import audioop
import base64
import contextlib
import fcntl
import json
import os
import select
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

try:
    import websocket
except ImportError as exc:  # pragma: no cover
    print(
        "ERROR: websocket-client is required. Install: pip install websocket-client",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc

# EAGI audio on file descriptor 3 (Asterisk convention).
EAGI_FD = 3
SAMPLE_RATE = 8000
# 20 ms @ 8 kHz 16-bit mono.
SLIN_CHUNK_BYTES = 320
# 20 ms @ 8 kHz ulaw.
ULAW_CHUNK_BYTES = 160

DEFAULT_LOG_PATH = Path("/var/log/ai-fronter-bridge.log")
DEFAULT_CONFIG_PATHS = (
    Path("/etc/ai-fronter/agent_port_map.json"),
    Path(__file__).resolve().parent / "agent_port_map.json",
)


def _log(msg: str) -> None:
    pid = os.getpid()
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{pid}] {msg}\n"
    with _log_lock:
        log_path = os.getenv("AI_FRONTER_LOG", "").strip() or str(DEFAULT_LOG_PATH)
        try:
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(line)
                fh.flush()
        except OSError:
            sys.stderr.write(line)
            sys.stderr.flush()


_log_lock = threading.Lock()


class _CallLock:
    """One bridge instance per uniqueid (guards against duplicate EAGI launches)."""

    def __init__(self, unique_id: str) -> None:
        safe = unique_id.replace(".", "_").replace("/", "_")
        self._path = Path(f"/tmp/ai-fronter-{safe}.lock")
        self._fh = None

    def acquire(self) -> bool:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self._path, "w", encoding="utf-8")
        try:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._fh.close()
            self._fh = None
            return False
        self._fh.write(f"{os.getpid()}\n")
        self._fh.flush()
        return True

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        self._fh.close()
        self._fh = None
        with contextlib.suppress(OSError):
            self._path.unlink(missing_ok=True)


def _bootstrap_gpu_silence(ws: websocket.WebSocket, *, chunks: int = 50) -> None:
    """Send ~1 s PCMU silence so the GPU telephony pipeline starts (matches --test-ws)."""
    silence_ulaw = b"\xff" * ULAW_CHUNK_BYTES
    for i in range(chunks):
        payload = base64.b64encode(silence_ulaw).decode("ascii")
        ws.send(_media_message(payload))
        if i == 0:
            _log("Sent bootstrap silence to GPU")
        time.sleep(0.02)


class AGI:
    """Minimal Asterisk AGI client (stdin/stdout protocol)."""

    def __init__(self) -> None:
        self.env: dict[str, str] = {}
        self._read_env()

    def _read_env(self) -> None:
        while True:
            line = sys.stdin.readline()
            if not line or line.strip() == "":
                break
            key, _, value = line.partition(":")
            self.env[key.strip()] = value.strip()

    def command(self, cmd: str) -> str:
        sys.stdout.write(cmd.strip() + "\n")
        sys.stdout.flush()
        return sys.stdin.readline().strip()

    def get_variable(self, name: str) -> str:
        result = self.command(f"GET VARIABLE {name}")
        if "result=1" in result and "(" in result:
            return result.split("(", 1)[1].rstrip(")")
        return ""


def _load_config() -> dict[str, Any]:
    explicit = os.getenv("AI_FRONTER_CONFIG", "").strip()
    paths = [Path(explicit)] if explicit else list(DEFAULT_CONFIG_PATHS)
    for path in paths:
        if path.is_file():
            try:
                with path.open(encoding="utf-8") as fh:
                    data = json.load(fh)
                _log(f"Loaded config {path}")
                return data if isinstance(data, dict) else {}
            except (OSError, json.JSONDecodeError) as exc:
                _log(f"Config read failed ({path}): {exc}")
    return {}


def _fetch_supervisor_port(gpu_host: str, supervisor_port: int, agent_user: str) -> int | None:
    url = f"http://{gpu_host}:{supervisor_port}/status"
    try:
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=8) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (URLError, OSError, json.JSONDecodeError, TimeoutError) as exc:
        _log(f"Supervisor lookup failed ({url}): {exc}")
        return None

    for worker in payload.get("workers") or []:
        if str(worker.get("vicidial_agent_user") or "") == agent_user:
            port = worker.get("media_port")
            if port is not None:
                return int(port)
    return None


def resolve_media_port(agent_user: str) -> tuple[str, int]:
    override_port = os.getenv("AI_FRONTER_MEDIA_PORT", "").strip()
    if override_port.isdigit():
        host = os.getenv("AI_FRONTER_GPU_HOST", "127.0.0.1").strip() or "127.0.0.1"
        return host, int(override_port)

    cfg = _load_config()
    gpu_host = os.getenv("AI_FRONTER_GPU_HOST", "").strip() or str(cfg.get("gpu_host") or "127.0.0.1")
    supervisor_port = int(cfg.get("supervisor_port") or 8770)

    agents = cfg.get("agents") or {}
    if agent_user in agents:
        return gpu_host, int(agents[agent_user])

    live_port = _fetch_supervisor_port(gpu_host, supervisor_port, agent_user)
    if live_port is not None:
        return gpu_host, live_port

    raise RuntimeError(
        f"No media port for ViciDial agent {agent_user!r}. "
        f"Set AI_FRONTER_MEDIA_PORT or add to agent_port_map.json, "
        f"or ensure GPU supervisor /status lists this agent."
    )


def build_telnyx_connected() -> dict[str, str]:
    return {"event": "connected", "version": "1.0.0"}


def build_telnyx_start(
    *,
    stream_id: str,
    call_control_id: str,
    caller: str,
    callee: str,
) -> dict[str, Any]:
    return {
        "event": "start",
        "sequence_number": "1",
        "stream_id": stream_id,
        "start": {
            "call_control_id": call_control_id,
            "from": caller or "unknown",
            "to": callee or "unknown",
            "media_format": {
                "encoding": "PCMU",
                "sample_rate": SAMPLE_RATE,
                "channels": 1,
            },
        },
    }


def _send_telnyx_handshake(
    ws: websocket.WebSocket,
    *,
    stream_id: str,
    call_control_id: str,
    caller: str,
    callee: str,
) -> None:
    """Send connected + start so pipecat parse_telephony_websocket reads both."""
    ws.send(json.dumps(build_telnyx_connected()))
    ws.send(
        json.dumps(
            build_telnyx_start(
                stream_id=stream_id,
                call_control_id=call_control_id,
                caller=caller,
                callee=callee,
            )
        )
    )


def _eagi_format() -> str:
    fmt = os.getenv("AI_FRONTER_EAGI_FORMAT", "slin").strip().lower()
    if fmt not in ("slin", "ulaw"):
        fmt = "slin"
    return fmt


def _resolve_eagi_format(agi: AGI) -> str:
    """Asterisk EAGI fd 3 is signed-linear PCM @ 8 kHz (not ulaw)."""
    channel_fmt = ""
    for name in ("AI_FRONTER_EAGI_FORMAT", "__AI_FRONTER_EAGI_FORMAT"):
        channel_fmt = agi.get_variable(name).strip().lower()
        if channel_fmt:
            break
    fmt = _eagi_format()
    if channel_fmt and channel_fmt != fmt:
        _log(
            f"NOTE: channel {name}={channel_fmt} ignored — "
            f"Asterisk EAGI fd 3 uses slin; using {fmt}"
        )
    else:
        _log(f"EAGI audio format={fmt}")
    return fmt


def _probe_eagi_fd(agi: AGI) -> bool:
    """Verify Asterisk passed a writable EAGI audio fd before opening GPU WebSocket."""
    enhanced = agi.env.get("agi_enhanced", "")
    network = agi.env.get("agi_network", "")
    _log(f"AGI env enhanced={enhanced!r} network={network!r} channel={agi.env.get('agi_channel', '?')}")
    if not enhanced:
        _log("WARNING: agi_enhanced missing — was this invoked with EAGI() not AGI()?")

    try:
        st = os.fstat(EAGI_FD)
        _log(f"EAGI fd {EAGI_FD} open (size={st.st_size})")
    except OSError as exc:
        _log(f"EAGI fd {EAGI_FD} unavailable: {exc}")
        return False

    try:
        silence = b"\x00" * SLIN_CHUNK_BYTES
        wrote = os.write(EAGI_FD, silence)
        _log(f"EAGI fd write probe OK ({wrote} bytes slin)")
        return True
    except OSError as exc:
        _log(f"EAGI fd write probe FAILED: {exc}")
        return False


def _slin_to_ulaw_payload(chunk: bytes) -> str | None:
    if not chunk:
        return None
    if len(chunk) % 2:
        chunk = chunk[:-1]
    if not chunk:
        return None
    ulaw = audioop.lin2ulaw(chunk, 2)
    return base64.b64encode(ulaw).decode("ascii")


def _ulaw_payload_to_eagi(ulaw: bytes, *, eagi_fmt: str) -> bytes:
    if eagi_fmt == "ulaw":
        return ulaw
    return audioop.ulaw2lin(ulaw, 2)


def _parse_gpu_media(raw: str | bytes) -> bytes | None:
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if msg.get("event") != "media":
        return None
    payload_b64 = (msg.get("media") or {}).get("payload")
    if not payload_b64:
        return None
    return base64.b64decode(payload_b64)


def _media_message(payload_b64: str) -> str:
    return json.dumps({"event": "media", "media": {"payload": payload_b64}})


class GpuBridge:
    """Bidirectional bridge: EAGI fd ↔ GPU WebSocket (Telnyx media JSON)."""

    def __init__(
        self,
        *,
        ws_url: str,
        stream_id: str,
        call_control_id: str,
        caller: str,
        callee: str,
        eagi_fmt: str,
    ) -> None:
        self.ws_url = ws_url
        self.stream_id = stream_id
        self.call_control_id = call_control_id
        self.caller = caller
        self.callee = callee
        self.eagi_fmt = eagi_fmt
        self._ws: websocket.WebSocket | None = None
        self._stop = threading.Event()
        self._recv_thread: threading.Thread | None = None
        self._wrote_audio = False
        self._sent_caller_audio = False
        self._gpu_media_packets = 0
        self._eagi_fd_broken = False

    def _write_ulaw_to_eagi(self, ulaw: bytes) -> bool:
        if self._eagi_fd_broken:
            return False
        out = _ulaw_payload_to_eagi(ulaw, eagi_fmt=self.eagi_fmt)
        if not out:
            return False
        try:
            os.write(EAGI_FD, out)
            self._gpu_media_packets += 1
            if not self._wrote_audio:
                self._wrote_audio = True
                _log(f"EAGI wrote first bot audio ({len(out)} bytes)")
            return True
        except OSError as exc:
            if not self._eagi_fd_broken:
                _log(f"EAGI write failed: {exc}")
                self._eagi_fd_broken = True
            self._stop.set()
            return False

    def _handle_gpu_raw(self, raw: str | bytes) -> bool:
        ulaw = _parse_gpu_media(raw)
        if ulaw is None:
            return False
        return self._write_ulaw_to_eagi(ulaw)

    def _sync_greeting_from_gpu(self, *, chunks: int | None = None) -> bool:
        """Mirror --test-ws: send silence and recv greeting in the main thread."""
        assert self._ws is not None
        ws = self._ws
        if chunks is None:
            chunks = int(os.getenv("AI_FRONTER_GREETING_CHUNKS", "500") or "500")
        silence_ulaw = b"\xff" * ULAW_CHUNK_BYTES
        got = False
        for i in range(chunks):
            ws.send(_media_message(base64.b64encode(silence_ulaw).decode("ascii")))
            time.sleep(0.02)
            try:
                ws.settimeout(0.05)
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            if not raw:
                _log("GPU WebSocket closed during sync greeting")
                self._stop.set()
                break
            if self._handle_gpu_raw(raw):
                got = True
        if got:
            _log(f"Sync greeting OK ({self._gpu_media_packets} packets to EAGI so far)")
        return got

    def connect(self) -> None:
        timeout = float(os.getenv("AI_FRONTER_WS_TIMEOUT", "8") or "8")
        _log(f"Connecting WebSocket {self.ws_url}")
        self._ws = websocket.create_connection(self.ws_url, timeout=timeout)
        _send_telnyx_handshake(
            self._ws,
            stream_id=self.stream_id,
            call_control_id=self.call_control_id,
            caller=self.caller,
            callee=self.callee,
        )
        _log(f"Sent Telnyx connected+start stream_id={self.stream_id}")
        time.sleep(0.05)
        if not self._sync_greeting_from_gpu():
            _log("WARNING: no bot audio from GPU during sync greeting (check GPU worker log)")
        self._recv_thread = threading.Thread(target=self._recv_loop, name="gpu-ws-recv", daemon=True)
        self._recv_thread.start()

    def _recv_loop(self) -> None:
        assert self._ws is not None
        ws = self._ws
        eagi_fd = EAGI_FD
        try:
            while not self._stop.is_set():
                ws.settimeout(0.5)
                try:
                    raw = ws.recv()
                except websocket.WebSocketTimeoutException:
                    continue
                if not raw:
                    _log("GPU WebSocket closed (recv empty)")
                    self._stop.set()
                    break
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                event = msg.get("event")
                if event == "media":
                    if self._handle_gpu_raw(raw):
                        pass
                elif event == "clear":
                    _log("GPU sent clear (interruption)")
                elif event == "stop":
                    _log("GPU sent stop")
                    self._stop.set()
                    break
        except Exception as exc:  # noqa: BLE001
            if not self._stop.is_set():
                _log(f"GPU recv error: {exc}")
            self._stop.set()

    def pump_caller_audio(self) -> None:
        assert self._ws is not None
        ws = self._ws
        eagi_fd = EAGI_FD
        read_size = ULAW_CHUNK_BYTES if self.eagi_fmt == "ulaw" else SLIN_CHUNK_BYTES

        while not self._stop.is_set():
            ready, _, _ = select.select([eagi_fd], [], [], 0.2)
            if not ready:
                # Keep GPU pipeline alive between utterances (Telnyx-style keepalive).
                try:
                    silence = base64.b64encode(b"\xff" * ULAW_CHUNK_BYTES).decode("ascii")
                    ws.send(_media_message(silence))
                except websocket.WebSocketException:
                    break
                continue
            try:
                chunk = os.read(eagi_fd, read_size)
            except OSError as exc:
                _log(f"EAGI read ended: {exc}")
                break
            if not chunk:
                _log("EAGI read EOF")
                break

            if self.eagi_fmt == "ulaw":
                payload_b64 = base64.b64encode(chunk).decode("ascii")
            else:
                payload_b64 = _slin_to_ulaw_payload(chunk)
            if payload_b64:
                try:
                    ws.send(_media_message(payload_b64))
                    if not self._sent_caller_audio:
                        self._sent_caller_audio = True
                        _log(f"EAGI sent first caller audio to GPU ({len(chunk)} bytes)")
                except websocket.WebSocketException as exc:
                    _log(f"GPU send failed: {exc}")
                    break

    def close(self) -> None:
        self._stop.set()
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:
                pass
        if self._recv_thread is not None:
            self._recv_thread.join(timeout=2)


def run_eagi(agent_user: str) -> int:
    agi = AGI()
    unique_id = agi.env.get("agi_uniqueid") or str(uuid.uuid4())
    call_lock = _CallLock(unique_id)
    if not call_lock.acquire():
        _log(f"EAGI duplicate launch rejected uniqueid={unique_id}")
        return 0

    caller = agi.env.get("agi_callerid") or agi.get_variable("CALLERID(num)")
    callee = agi.env.get("agi_extension") or agent_user
    channel = agi.env.get("agi_channel") or "?"

    _log(
        f"EAGI start agent={agent_user} uniqueid={unique_id} "
        f"caller={caller} channel={channel}"
    )

    if not _probe_eagi_fd(agi):
        agi.command("VERBOSE \"AI Fronter: EAGI audio fd not writable\" 1")
        return 1

    try:
        try:
            gpu_host, media_port = resolve_media_port(agent_user)
        except RuntimeError as exc:
            _log(f"ERROR: {exc}")
            agi.command("VERBOSE \"AI Fronter: no GPU port for agent\" 1")
            return 1

        ws_url = f"ws://{gpu_host}:{media_port}/ws"
        stream_id = f"vd-{agent_user}-{unique_id}"
        # Match --test-ws: call_control_id == stream_id (pipecat/Telnyx serializer expects this).
        call_control_id = stream_id

        bridge = GpuBridge(
            ws_url=ws_url,
            stream_id=stream_id,
            call_control_id=call_control_id,
            caller=caller,
            callee=callee,
            eagi_fmt=_resolve_eagi_format(agi),
        )

        try:
            bridge.connect()
        except Exception as exc:  # noqa: BLE001
            _log(f"WebSocket connect failed: {exc}")
            agi.command(f"VERBOSE \"AI Fronter: GPU unreachable {gpu_host}:{media_port}\" 1")
            return 1

        agi.command("VERBOSE \"AI Fronter: bridged to GPU\" 1")
        if bridge._gpu_media_packets == 0:
            agi.command("VERBOSE \"AI Fronter: waiting for bot greeting\" 1")

        try:
            bridge.pump_caller_audio()
        finally:
            bridge.close()
            _log(
                f"Bridge session ended (gpu_packets={bridge._gpu_media_packets}, "
                f"caller_sent={bridge._sent_caller_audio})"
            )
    finally:
        call_lock.release()

    return 0


def run_test_ws(agent_user: str) -> int:
    """Connect to GPU, send start, wait briefly — no Asterisk required."""
    gpu_host, media_port = resolve_media_port(agent_user)
    ws_url = f"ws://{gpu_host}:{media_port}/ws"
    stream_id = f"test-{uuid.uuid4().hex[:8]}"
    _log(f"Test mode: {ws_url}")

    ws = websocket.create_connection(ws_url, timeout=8)
    _send_telnyx_handshake(
        ws,
        stream_id=stream_id,
        call_control_id=stream_id,
        caller="+15551234567",
        callee=agent_user,
    )
    _log("Connected+start sent — waiting for media (Ctrl+C to exit)...")
    time.sleep(0.05)

    chunks = int(os.getenv("AI_FRONTER_GREETING_CHUNKS", "500") or "500")
    silence_ulaw = b"\xff" * ULAW_CHUNK_BYTES
    got = False
    for _ in range(chunks):
        payload = base64.b64encode(silence_ulaw).decode("ascii")
        ws.send(_media_message(payload))
        time.sleep(0.02)
        try:
            ws.settimeout(0.05)
            msg = ws.recv()
            if msg:
                data = json.loads(msg)
                if data.get("event") == "media":
                    _log("Received bot audio from GPU (OK)")
                    got = True
                    break
        except websocket.WebSocketTimeoutException:
            pass

    try:
        ws.send(json.dumps({"event": "stop", "stream_id": stream_id}))
        time.sleep(2.0)
    except websocket.WebSocketException:
        pass
    ws.close()
    if not got:
        _log("WARNING: no bot audio from GPU during test-ws")
    _log("Test complete")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="AI Fronter ViciDial EAGI → GPU WebSocket bridge")
    parser.add_argument(
        "agent_user",
        nargs="?",
        help="ViciDial agent login (e.g. 6666). Passed from EAGI dialplan arg.",
    )
    parser.add_argument(
        "--test-ws",
        action="store_true",
        help="Test WebSocket to GPU without Asterisk (requires agent_user).",
    )
    args = parser.parse_args()

    agent_user = (args.agent_user or os.getenv("AI_FRONTER_AGENT_USER") or "").strip()
    if not agent_user:
        _log("ERROR: agent_user required (CLI arg or AI_FRONTER_AGENT_USER)")
        return 1

    if args.test_ws:
        return run_test_ws(agent_user)

    return run_eagi(agent_user)


if __name__ == "__main__":
    raise SystemExit(main())
