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

AudioSocket (when EAGI fd 3 is broken — CyburDial/Asterisk 18+):
  python3 ai-fronter-bridge.py --serve-audiosocket 6666
  Dialplan: Answer() then AudioSocket(${UUID()},127.0.0.1:9092)
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
import socket
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

# AudioSocket TLV types (https://docs.asterisk.org/Configuration/Channel-Drivers/AudioSocket/)
_AS_TYPE_TERM = 0x00
_AS_TYPE_UUID = 0x01
_AS_TYPE_DTMF = 0x03
_AS_TYPE_AUDIO = 0x10
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


def _log(msg: str, *, also_stderr: bool = False) -> None:
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
    if also_stderr:
        sys.stderr.write(line)
        sys.stderr.flush()


_log_lock = threading.Lock()
_audiosocket_lock_guard = threading.Lock()
_audiosocket_gpu_locks: dict[str, threading.Lock] = {}


def _audiosocket_gpu_lock(agent_user: str) -> threading.Lock:
    with _audiosocket_lock_guard:
        lock = _audiosocket_gpu_locks.get(agent_user)
        if lock is None:
            lock = threading.Lock()
            _audiosocket_gpu_locks[agent_user] = lock
        return lock


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


def _wait_gpu_ready(gpu_host: str, media_port: int, *, timeout_s: float = 20.0) -> bool:
    """Wait until /health reports ready (not busy on another call)."""
    url = f"http://{gpu_host}:{media_port}/health"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            req = Request(url, headers={"Accept": "application/json"})
            with urlopen(req, timeout=3) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            ready = payload.get("ready", True)
            if ready is True or str(ready).lower() == "true":
                return True
            _log("GPU worker busy (ready=false) — waiting for prior call to finish")
        except (URLError, OSError, json.JSONDecodeError, TimeoutError) as exc:
            _log(f"GPU health check failed ({url}): {exc}")
        time.sleep(0.5)
    return False


def build_telnyx_connected() -> dict[str, str]:
    return {"event": "connected", "version": "1.0.0"}


def build_telnyx_start(
    *,
    stream_id: str,
    call_control_id: str,
    caller: str,
    callee: str,
    vicidial_call_id: str = "",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
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
    vd_id = (vicidial_call_id or "").strip()
    if vd_id:
        payload["vicidial_call_id"] = vd_id
        payload["start"]["vicidial_call_id"] = vd_id
    return payload


def _send_telnyx_handshake(
    ws: websocket.WebSocket,
    *,
    stream_id: str,
    call_control_id: str,
    caller: str,
    callee: str,
    vicidial_call_id: str = "",
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
                vicidial_call_id=vicidial_call_id,
            )
        )
    )


def _looks_like_vicidial_call_id(value: str) -> bool:
    """ViciDial remote-agent call IDs start with V or Y and are ~20 chars."""
    token = (value or "").strip()
    if len(token) < 12:
        return False
    return token[0] in ("V", "Y") and token[1:].replace("-", "").isalnum()


def _lookup_vicidial_call_id(agent_user: str) -> str:
    """Read active remote-agent call ID from vicidial_live_agents (AudioSocket path)."""
    if os.getenv("AI_FRONTER_SKIP_VD_CALL_ID_LOOKUP", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return ""
    mysql_user = os.getenv("AI_FRONTER_MYSQL_USER", "").strip()
    mysql_pass = os.getenv("AI_FRONTER_MYSQL_PASS", "").strip()
    mysql_db = os.getenv("AI_FRONTER_MYSQL_DB", "asterisk").strip() or "asterisk"
    if not mysql_user:
        for path in (
            Path("/etc/astguiclient.conf"),
            Path("/usr/share/astguiclient/ADMIN_settings.txt"),
        ):
            if not path.is_file():
                continue
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line.startswith("VARDB_user") and "=" in line:
                    mysql_user = line.split("=", 1)[1].strip()
                elif line.startswith("VARDB_pass") and "=" in line:
                    mysql_pass = line.split("=", 1)[1].strip()
                elif line.startswith("VARDB_database") and "=" in line:
                    mysql_db = line.split("=", 1)[1].strip() or mysql_db
            if mysql_user:
                break
    if not mysql_user:
        return ""
    sql = (
        "SELECT callerid FROM vicidial_live_agents "
        f"WHERE user='{agent_user.replace(chr(39), chr(39) + chr(39))}' "
        "AND callerid IS NOT NULL AND callerid != '' LIMIT 1;"
    )
    try:
        import subprocess

        proc = subprocess.run(
            ["mysql", "-N", "-B", "-u", mysql_user, f"-p{mysql_pass}", mysql_db, "-e", sql],
            capture_output=True,
            text=True,
            timeout=5,
        )
        candidate = (proc.stdout or "").strip().splitlines()[0].strip() if proc.stdout else ""
        if _looks_like_vicidial_call_id(candidate):
            _log(f"ViciDial call ID from live_agents: {candidate}")
            return candidate
    except Exception as exc:  # noqa: BLE001
        _log(f"ViciDial call ID lookup failed: {exc}")
    return ""


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


def _as_recv_exact(conn: socket.socket, nbytes: int) -> bytes | None:
    buf = bytearray()
    while len(buf) < nbytes:
        try:
            chunk = conn.recv(nbytes - len(buf))
        except OSError:
            return None
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)


def _as_read_frame(conn: socket.socket) -> tuple[int | None, bytes]:
    header = _as_recv_exact(conn, 3)
    if not header:
        return None, b""
    msg_type = header[0]
    length = int.from_bytes(header[1:3], "big")
    if length == 0:
        return msg_type, b""
    payload = _as_recv_exact(conn, length)
    if payload is None:
        return None, b""
    return msg_type, payload


def _as_write_frame(conn: socket.socket, msg_type: int, payload: bytes) -> bool:
    try:
        conn.sendall(bytes([msg_type]) + len(payload).to_bytes(2, "big") + payload)
        return True
    except OSError as exc:
        _log(f"AudioSocket write failed: {exc}")
        return False


def _as_uuid_to_str(payload: bytes) -> str:
    if len(payload) == 16:
        return str(uuid.UUID(bytes=payload))
    try:
        return payload.decode("utf-8", errors="replace").strip()
    except Exception:
        return payload.hex()


class AudioSocketGpuBridge:
    """Bidirectional bridge: AudioSocket TCP (slin) ↔ GPU WebSocket."""

    def __init__(
        self,
        *,
        conn: socket.socket,
        ws_url: str,
        stream_id: str,
        call_control_id: str,
        caller: str,
        callee: str,
        vicidial_call_id: str = "",
    ) -> None:
        self._conn = conn
        self.ws_url = ws_url
        self.stream_id = stream_id
        self.call_control_id = call_control_id
        self.caller = caller
        self.callee = callee
        self.vicidial_call_id = (vicidial_call_id or "").strip()
        self._ws: websocket.WebSocket | None = None
        self._stop = threading.Event()
        self._recv_thread: threading.Thread | None = None
        self._wrote_audio = False
        self._sent_caller_audio = False
        self._gpu_media_packets = 0
        self._write_lock = threading.Lock()
        self._recv_thread_started = False
        self._last_as_write_time = 0.0

    def _touch_as_write(self) -> None:
        self._last_as_write_time = time.monotonic()

    def _maybe_keepalive_as(self) -> None:
        """Asterisk needs outbound frames even while we read caller audio."""
        if time.monotonic() - self._last_as_write_time < 0.018:
            return
        if self._send_as_silence():
            self._touch_as_write()

    def _as_realtime_pace(self) -> bool:
        return os.getenv("AI_FRONTER_AS_REALTIME_PACE", "true").strip().lower() in (
            "1",
            "true",
            "yes",
        )

    def _send_gpu_silence(self) -> None:
        if self._ws is None or self._stop.is_set():
            return
        silence = base64.b64encode(b"\xff" * ULAW_CHUNK_BYTES).decode("ascii")
        try:
            self._ws.send(_media_message(silence))
        except websocket.WebSocketException:
            self._stop.set()

    def _write_ulaw_to_as(self, ulaw: bytes, *, paced: bool | None = None) -> bool:
        if not ulaw:
            return False
        slin = audioop.ulaw2lin(ulaw, 2)
        chunk = SLIN_CHUNK_BYTES
        if paced is None:
            paced = self._as_realtime_pace()
        wrote = False
        with self._write_lock:
            for offset in range(0, len(slin), chunk):
                frame = slin[offset : offset + chunk]
                if not _as_write_frame(self._conn, _AS_TYPE_AUDIO, frame):
                    self._stop.set()
                    return False
                wrote = True
                self._touch_as_write()
                if paced:
                    time.sleep(0.02)
        if not wrote:
            return False
        self._gpu_media_packets += 1
        if not self._wrote_audio:
            self._wrote_audio = True
            _log(f"AudioSocket wrote first bot audio ({len(slin)} bytes slin, chunked)")
        return True

    def _handle_gpu_raw(self, raw: str | bytes, *, paced: bool | None = None) -> bool:
        ulaw = _parse_gpu_media(raw)
        if ulaw is None:
            return False
        return self._write_ulaw_to_as(ulaw, paced=paced)

    def _sync_greeting_from_gpu(self, *, chunks: int | None = None) -> bool:
        assert self._ws is not None
        ws = self._ws
        if chunks is None:
            chunks = int(os.getenv("AI_FRONTER_GREETING_CHUNKS", "500") or "500")
        silence_ulaw = b"\xff" * ULAW_CHUNK_BYTES
        got = False
        idle_after_audio = 0
        max_idle = int(os.getenv("AI_FRONTER_GREETING_IDLE_CHUNKS", "60") or "60")
        min_messages = int(os.getenv("AI_FRONTER_GREETING_MIN_MESSAGES", "1") or "1")
        audio_messages = 0
        for _ in range(chunks):
            ws.send(_media_message(base64.b64encode(silence_ulaw).decode("ascii")))
            time.sleep(0.02)
            try:
                ws.settimeout(0.05)
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                if got and audio_messages >= min_messages:
                    idle_after_audio += 1
                    if idle_after_audio >= max_idle:
                        break
                continue
            idle_after_audio = 0
            if not raw:
                _log("GPU WebSocket closed during sync greeting")
                self._stop.set()
                break
            if self._handle_gpu_raw(raw, paced=False):
                got = True
                audio_messages += 1
        if got:
            _log(
                f"Sync greeting OK ({audio_messages} GPU audio messages, "
                f"{self._gpu_media_packets} writes to AudioSocket)"
            )
        return got

    def _start_recv_thread(self) -> None:
        if self._recv_thread_started:
            return
        self._recv_thread = threading.Thread(
            target=self._recv_loop, name="gpu-ws-recv", daemon=True
        )
        self._recv_thread.start()
        self._recv_thread_started = True

    def _wait_for_greeting_audio(self) -> bool:
        """Feed GPU silence while recv thread pace-writes greeting (matches direct Telnyx timing)."""
        min_messages = int(os.getenv("AI_FRONTER_GREETING_MIN_MESSAGES", "2") or "2")
        wait_s = float(os.getenv("AI_FRONTER_GREETING_WAIT_S", "20") or "20")
        max_idle = int(os.getenv("AI_FRONTER_GREETING_IDLE_CHUNKS", "50") or "50")
        deadline = time.time() + wait_s
        last_count = 0
        idle_after = 0
        while time.time() < deadline and not self._stop.is_set():
            self._send_gpu_silence()
            time.sleep(0.02)
            count = self._gpu_media_packets
            if count >= min_messages:
                _log(
                    f"Greeting ready ({count} GPU audio messages, "
                    f"paced={self._as_realtime_pace()})"
                )
                return True
            if count > last_count:
                last_count = count
                idle_after = 0
            elif count > 0:
                idle_after += 1
                if idle_after >= max_idle:
                    _log(
                        f"Greeting idle after {count} message(s) "
                        f"(wanted {min_messages}) — continuing call"
                    )
                    return True
        if self._wrote_audio:
            _log(
                f"Greeting partial ({self._gpu_media_packets} messages) "
                f"before wait expired ({wait_s:.0f}s)"
            )
            return True
        return False

    def _open_ws_only(self) -> None:
        timeout = float(os.getenv("AI_FRONTER_WS_TIMEOUT", "8") or "8")
        _log(f"Connecting WebSocket {self.ws_url}")
        self._ws = websocket.create_connection(self.ws_url, timeout=timeout)
        _send_telnyx_handshake(
            self._ws,
            stream_id=self.stream_id,
            call_control_id=self.call_control_id,
            caller=self.caller,
            callee=self.callee,
            vicidial_call_id=self.vicidial_call_id,
        )
        _log(f"Sent Telnyx connected+start stream_id={self.stream_id}")
        time.sleep(float(os.getenv("AI_FRONTER_HANDSHAKE_WAIT_S", "2") or "2"))

    def _open_ws_and_greeting(self) -> bool:
        self._open_ws_only()
        self._start_recv_thread()
        return self._wait_for_greeting_audio()

    def _close_ws(self) -> None:
        if self._recv_thread is not None:
            self._recv_thread.join(timeout=2)
            self._recv_thread = None
        self._recv_thread_started = False
        if self._ws is not None:
            with contextlib.suppress(Exception):
                self._ws.close()
            self._ws = None

    def connect(self) -> None:
        gpu_host = self.ws_url.split("//", 1)[-1].split("/", 1)[0]
        host_part, _, port_part = gpu_host.rpartition(":")
        media_port = int(port_part or "8800")
        wait_s = float(os.getenv("AI_FRONTER_GPU_READY_WAIT_S", "20") or "20")
        if not _wait_gpu_ready(host_part or "127.0.0.1", media_port, timeout_s=wait_s):
            _log(
                f"WARNING: GPU not ready after {wait_s:.0f}s "
                "(prior call may still be running on worker)"
            )

        retries = int(os.getenv("AI_FRONTER_WS_CONNECT_RETRIES", "2") or "2")
        got = False
        for attempt in range(1, max(1, retries) + 1):
            if attempt > 1:
                _log(f"Retrying GPU WebSocket (attempt {attempt}/{retries})")
                time.sleep(1.0)
            try:
                got = self._open_ws_and_greeting()
            except Exception as exc:  # noqa: BLE001
                _log(f"WebSocket connect failed: {exc}")
                self._close_ws()
                if attempt >= retries:
                    raise
                continue
            if got:
                break
            _log("WARNING: no bot audio from GPU during greeting wait (check GPU worker log)")
            self._close_ws()
            if attempt >= retries:
                break

        if self._ws is None:
            raise websocket.WebSocketException("GPU WebSocket not connected")

    def _recv_loop(self) -> None:
        assert self._ws is not None
        ws = self._ws
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
                if msg.get("event") == "media":
                    self._handle_gpu_raw(raw)
                elif msg.get("event") == "stop":
                    _log("GPU sent stop")
                    self._stop.set()
                    break
        except Exception as exc:  # noqa: BLE001
            if not self._stop.is_set():
                _log(f"GPU recv error: {exc}")
            self._stop.set()

    def _send_as_silence(self) -> bool:
        """Keep Asterisk AudioSocket fed between bot utterances (avoids 'Failed to receive frame')."""
        silence_slin = b"\x00" * SLIN_CHUNK_BYTES
        with self._write_lock:
            ok = _as_write_frame(self._conn, _AS_TYPE_AUDIO, silence_slin)
        if ok:
            self._touch_as_write()
        return ok

    def pump_caller_audio(self) -> None:
        assert self._ws is not None
        ws = self._ws
        self._conn.settimeout(0.02)
        silence = base64.b64encode(b"\xff" * ULAW_CHUNK_BYTES).decode("ascii")
        while not self._stop.is_set():
            self._maybe_keepalive_as()
            try:
                msg_type, payload = _as_read_frame(self._conn)
            except socket.timeout:
                try:
                    ws.send(_media_message(silence))
                except websocket.WebSocketException:
                    break
                continue
            except OSError as exc:
                _log(f"AudioSocket read ended: {exc}")
                break
            if msg_type is None:
                _log("AudioSocket read EOF")
                break
            if msg_type == _AS_TYPE_TERM:
                _log("AudioSocket terminate")
                break
            if msg_type == _AS_TYPE_AUDIO and payload:
                payload_b64 = _slin_to_ulaw_payload(payload)
                if payload_b64:
                    try:
                        ws.send(_media_message(payload_b64))
                        if not self._sent_caller_audio:
                            self._sent_caller_audio = True
                            _log(f"AudioSocket sent first caller audio ({len(payload)} bytes)")
                    except websocket.WebSocketException as exc:
                        _log(f"GPU send failed: {exc}")
                        break
            elif msg_type not in (_AS_TYPE_UUID, _AS_TYPE_DTMF):
                _log(f"AudioSocket ignoring frame type=0x{msg_type:02x}")

    def close(self) -> None:
        self._stop.set()
        self._close_ws()
        with contextlib.suppress(OSError):
            self._conn.close()


def _handle_audiosocket_client(conn: socket.socket, addr: tuple, agent_user: str) -> None:
    peer = f"{addr[0]}:{addr[1]}"
    _log(f"AudioSocket connect from {peer}")
    gpu_lock = _audiosocket_gpu_lock(agent_user)
    if not gpu_lock.acquire(blocking=False):
        _log(f"AudioSocket rejected: GPU session already active for agent {agent_user}")
        return
    try:
        msg_type, payload = _as_read_frame(conn)
        if msg_type != _AS_TYPE_UUID:
            _log(f"AudioSocket expected UUID frame, got 0x{msg_type!r}")
            return
        call_uuid = _as_uuid_to_str(payload)
        _log(f"AudioSocket call uuid={call_uuid}")

        try:
            gpu_host, media_port = resolve_media_port(agent_user)
        except RuntimeError as exc:
            _log(f"ERROR: {exc}")
            return

        stream_id = f"vd-{agent_user}-{call_uuid[:8]}"
        vd_call_id = _lookup_vicidial_call_id(agent_user)
        bridge = AudioSocketGpuBridge(
            conn=conn,
            ws_url=f"ws://{gpu_host}:{media_port}/ws",
            stream_id=stream_id,
            call_control_id=stream_id,
            caller=os.getenv("AI_FRONTER_DEFAULT_CALLER", "+15551234567"),
            callee=agent_user,
            vicidial_call_id=vd_call_id,
        )
        try:
            bridge.connect()
        except Exception as exc:  # noqa: BLE001
            _log(f"WebSocket connect failed: {exc}")
            return
        try:
            bridge.pump_caller_audio()
        finally:
            bridge.close()
            _log(
                f"AudioSocket session ended (gpu_packets={bridge._gpu_media_packets}, "
                f"caller_sent={bridge._sent_caller_audio})"
            )
    except Exception as exc:  # noqa: BLE001
        _log(f"AudioSocket handler error: {exc}")
    finally:
        gpu_lock.release()
        with contextlib.suppress(OSError):
            conn.close()


def run_audiosocket_server(agent_user: str) -> int:
    host = os.getenv("AI_FRONTER_AUDIOSOCKET_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = int(os.getenv("AI_FRONTER_AUDIOSOCKET_PORT", "9092") or "9092")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen(int(os.getenv("AI_FRONTER_AUDIOSOCKET_BACKLOG", "32") or "32"))
    _log(
        f"AudioSocket server on {host}:{port} agent={agent_user} (Ctrl+C to stop)",
        also_stderr=True,
    )
    try:
        while True:
            conn, addr = sock.accept()
            # Handle synchronously in the accept thread (same as --test-ws main thread).
            # Daemon worker threads broke WebSocket greeting recv on some hosts.
            _handle_audiosocket_client(conn, addr, agent_user)
    except KeyboardInterrupt:
        _log("AudioSocket server stopped")
    finally:
        sock.close()
    return 0


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
        vicidial_call_id: str = "",
    ) -> None:
        self.ws_url = ws_url
        self.stream_id = stream_id
        self.call_control_id = call_control_id
        self.caller = caller
        self.callee = callee
        self.eagi_fmt = eagi_fmt
        self.vicidial_call_id = (vicidial_call_id or "").strip()
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
            vicidial_call_id=self.vicidial_call_id,
        )
        _log(f"Sent Telnyx connected+start stream_id={self.stream_id}")
        # Allow GPU pipeline (Chatterbox prewarm/build) to start before bootstrap silence.
        time.sleep(float(os.getenv("AI_FRONTER_HANDSHAKE_WAIT_S", "2") or "2"))
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
    vd_call_id = (agi.get_variable("CALLERID(name)") or "").strip()
    if not _looks_like_vicidial_call_id(vd_call_id):
        vd_call_id = _lookup_vicidial_call_id(agent_user)
    callee = agi.env.get("agi_extension") or agent_user
    channel = agi.env.get("agi_channel") or "?"

    _log(
        f"EAGI start agent={agent_user} uniqueid={unique_id} "
        f"caller={caller} vd_call_id={vd_call_id or 'unset'} channel={channel}"
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
            vicidial_call_id=vd_call_id,
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
    """Connect to GPU, send start, wait for greeting — no Asterisk required."""
    gpu_host, media_port = resolve_media_port(agent_user)
    ws_url = f"ws://{gpu_host}:{media_port}/ws"
    stream_id = f"test-{uuid.uuid4().hex[:8]}"
    _log(f"Test mode: {ws_url}")
    _log("NOTE: do not run test-ws immediately before a live dial — it holds the GPU call slot")

    timeout = float(os.getenv("AI_FRONTER_WS_TIMEOUT", "8") or "8")
    ws = websocket.create_connection(ws_url, timeout=timeout)
    _send_telnyx_handshake(
        ws,
        stream_id=stream_id,
        call_control_id=stream_id,
        caller="+15551234567",
        callee=agent_user,
    )
    _log("Connected+start sent — waiting for media (Ctrl+C to exit)...")
    time.sleep(float(os.getenv("AI_FRONTER_HANDSHAKE_WAIT_S", "2") or "2"))

    chunks = int(os.getenv("AI_FRONTER_GREETING_CHUNKS", "200") or "200")
    silence_ulaw = b"\xff" * ULAW_CHUNK_BYTES
    got = False
    audio_messages = 0
    idle_after_audio = 0
    max_idle = int(os.getenv("AI_FRONTER_GREETING_IDLE_CHUNKS", "30") or "30")
    for _ in range(chunks):
        payload = base64.b64encode(silence_ulaw).decode("ascii")
        ws.send(_media_message(payload))
        time.sleep(0.02)
        try:
            ws.settimeout(0.05)
            msg = ws.recv()
        except websocket.WebSocketTimeoutException:
            if got:
                idle_after_audio += 1
                if idle_after_audio >= max_idle:
                    break
            continue
        idle_after_audio = 0
        if not msg:
            break
        try:
            data = json.loads(msg)
        except json.JSONDecodeError:
            continue
        if data.get("event") == "media":
            audio_messages += 1
            if not got:
                _log("Received bot audio from GPU (OK)")
            got = True

    try:
        ws.send(json.dumps({"event": "stop", "stream_id": stream_id}))
        time.sleep(0.5)
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
        "--serve-audiosocket",
        action="store_true",
        help="Run AudioSocket TCP server (replaces EAGI when fd 3 is broken).",
    )
    parser.add_argument(
        "--test-ws",
        action="store_true",
        help="Test WebSocket to GPU without Asterisk (requires agent_user).",
    )
    args = parser.parse_args()

    agent_user = (args.agent_user or os.getenv("AI_FRONTER_AGENT_USER") or "").strip()
    if not agent_user:
        _log(
            "ERROR: agent_user required (CLI arg or AI_FRONTER_AGENT_USER)",
            also_stderr=True,
        )
        return 1

    if args.serve_audiosocket:
        return run_audiosocket_server(agent_user)

    if args.test_ws:
        return run_test_ws(agent_user)

    return run_eagi(agent_user)


if __name__ == "__main__":
    raise SystemExit(main())
