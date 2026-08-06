#!/usr/bin/env python3
"""Repair ai-fronter-bridge.py keepalive (idempotent). Run on ViciDial as root."""
from pathlib import Path
import py_compile
import subprocess

PATH = Path("/usr/local/bin/ai-fronter-bridge.py")
text = PATH.read_text(encoding="utf-8")
changed = False

if "_last_as_write_time" not in text:
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
        raise SystemExit("ERROR: missing __init__ anchor")
    text = text.replace(needle, insert, 1)
    changed = True

if "_send_as_silence" not in text:
    anchor = "    def pump_caller_audio(self) -> None:"
    method = """    def _send_as_silence(self) -> bool:
        \"\"\"Keep Asterisk AudioSocket fed between bot utterances.\"\"\"
        silence_slin = b"\\x00" * SLIN_CHUNK_BYTES
        with self._write_lock:
            ok = _as_write_frame(self._conn, _AS_TYPE_AUDIO, silence_slin)
        if ok:
            self._touch_as_write()
        return ok

"""
    if anchor not in text:
        raise SystemExit("ERROR: missing pump_caller_audio anchor")
    text = text.replace(anchor, method + anchor, 1)
    changed = True

if "self._maybe_keepalive_as()" not in text:
    text = text.replace(
        "        while not self._stop.is_set():\n            try:",
        "        while not self._stop.is_set():\n            self._maybe_keepalive_as()\n            try:",
        1,
    )
    changed = True

if "self._touch_as_write()" not in text.split("_write_ulaw_to_as", 1)[-1][:800]:
    text = text.replace(
        """                wrote = True
                if paced:
                    time.sleep(0.02)
""",
        """                wrote = True
                self._touch_as_write()
                if paced:
                    time.sleep(0.02)
""",
        1,
    )
    changed = True

if "self._conn.settimeout(0.2)" in text:
    text = text.replace("self._conn.settimeout(0.2)", "self._conn.settimeout(0.02)", 1)
    changed = True

PATH.write_text(text, encoding="utf-8")
py_compile.compile(str(PATH), doraise=True)
print("OK" if changed else "Already complete")
for pat in ("_send_as_silence", "_maybe_keepalive_as", "_touch_as_write"):
    subprocess.run(["grep", "-c", pat, str(PATH)], check=False)
