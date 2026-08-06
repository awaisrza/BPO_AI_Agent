#!/usr/bin/env python3
"""Patch installed ai-fronter-bridge.py with AudioSocket keepalive fix."""
from pathlib import Path

PATH = Path("/usr/local/bin/ai-fronter-bridge.py")
text = PATH.read_text(encoding="utf-8")

if "_maybe_keepalive_as" in text and "_send_as_silence" in text:
    print("Already patched.")
    raise SystemExit(0)

needle = "        self._recv_thread_started = False\n"
insert = """        self._recv_thread_started = False
        self._last_as_write_time = 0.0

    def _touch_as_write(self) -> None:
        self._last_as_write_time = time.monotonic()

    def _maybe_keepalive_as(self) -> None:
        if time.monotonic() - self._last_as_write_time < 0.018:
            return
        if self._send_as_silence():
            self._touch_as_write()

"""
if needle not in text:
    raise SystemExit("ERROR: could not find __init__ anchor — update bridge manually")
text = text.replace(needle, insert, 1)

old_silence = """    def _send_as_silence(self) -> bool:
        \"\"\"Keep Asterisk AudioSocket fed between bot utterances (avoids 'Failed to receive frame').\"\"\"
        silence_slin = b"\\x00" * SLIN_CHUNK_BYTES
        with self._write_lock:
            return _as_write_frame(self._conn, _AS_TYPE_AUDIO, silence_slin)
"""
new_silence = """    def _send_as_silence(self) -> bool:
        \"\"\"Keep Asterisk AudioSocket fed between bot utterances (avoids 'Failed to receive frame').\"\"\"
        silence_slin = b"\\x00" * SLIN_CHUNK_BYTES
        with self._write_lock:
            ok = _as_write_frame(self._conn, _AS_TYPE_AUDIO, silence_slin)
        if ok:
            self._touch_as_write()
        return ok
"""
if old_silence in text:
    text = text.replace(old_silence, new_silence, 1)
elif "_send_as_silence" not in text:
    anchor = "    def pump_caller_audio(self) -> None:"
    if anchor not in text:
        raise SystemExit("ERROR: missing pump_caller_audio — deploy full agi_bridge.py")
    text = text.replace(anchor, new_silence + "\n" + anchor, 1)

old_loop = """        while not self._stop.is_set():
            try:
                msg_type, payload = _as_read_frame(self._conn)
            except socket.timeout:
                try:
                    ws.send(_media_message(silence))
                except websocket.WebSocketException:
                    break
                self._send_as_silence()
                continue
"""
new_loop = """        while not self._stop.is_set():
            self._maybe_keepalive_as()
            try:
                msg_type, payload = _as_read_frame(self._conn)
            except socket.timeout:
                try:
                    ws.send(_media_message(silence))
                except websocket.WebSocketException:
                    break
                continue
"""
if old_loop in text:
    text = text.replace(old_loop, new_loop, 1)
elif "        while not self._stop.is_set():\n            try:" in text:
    text = text.replace(
        "        while not self._stop.is_set():\n            try:",
        "        while not self._stop.is_set():\n            self._maybe_keepalive_as()\n            try:",
        1,
    )

old_wrote = """                wrote = True
                if paced:
                    time.sleep(0.02)
"""
new_wrote = """                wrote = True
                self._touch_as_write()
                if paced:
                    time.sleep(0.02)
"""
if old_wrote in text:
    text = text.replace(old_wrote, new_wrote, 1)

PATH.write_text(text, encoding="utf-8")
import py_compile

py_compile.compile(str(PATH), doraise=True)
print("Patched OK — grep _maybe_keepalive_as:")
import subprocess

subprocess.run(["grep", "-n", "_maybe_keepalive_as", str(PATH)], check=False)
