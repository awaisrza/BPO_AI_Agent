#!/usr/bin/env python3
"""Fix no bot reply after greeting: BSSF after direct greeting + bridge caller pump."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# --- pipeline.py ---
pipe = ROOT / "app" / "pipeline.py"
ptext = pipe.read_text(encoding="utf-8")

on_direct = '''    async def on_direct_greeting_complete(self) -> None:
        """Opening line played via direct bulk PCM — match normal TTS end-of-playback."""
        if not PIPECAT_AVAILABLE:
            self._call.finish_bot_playback()
            return
        from pipecat.frames.frames import BotStoppedSpeakingFrame
        from pipecat.processors.frame_processor import FrameDirection

        logger.info("Direct bulk greeting finished — releasing caller turn")
        await self.process_frame(BotStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)

    async def _interrupt_and_handle_caller(self, text: str, direction) -> None:  # type: ignore[no-untyped-def]'''

if "async def on_direct_greeting_complete" not in ptext:
    anchor = "    async def _interrupt_and_handle_caller(self, text: str, direction) -> None:  # type: ignore[no-untyped-def]"
    if anchor not in ptext:
        raise SystemExit("pipeline interrupt anchor missing")
    ptext = ptext.replace(
        anchor,
        on_direct,
        1,
    )

old_drop = """                elif self._pending_caller_texts:
                    self._queue_pending_caller_text(text)
                return"""

new_drop = """                elif self._pending_caller_texts:
                    self._queue_pending_caller_text(text)
                else:
                    logger.info(
                        f"STT held (turn closed, state={self._call.state.value}): "
                        f"{text[:64]!r}"
                    )
                return"""

if old_drop in ptext and "STT held (turn closed" not in ptext:
    ptext = ptext.replace(old_drop, new_drop, 1)

pipe.write_text(ptext, encoding="utf-8")

# --- vicidial_session.py ---
vs = ROOT / "app" / "vicidial_session.py"
vtext = vs.read_text(encoding="utf-8")

old_tail = """            duration_ms = await send_direct_bulk_pcm(
                _ws_send_json,
                pcm,
                sample_rate=TELEPHONY_PIPELINE_RATE,
                encoding=bulk_encoding,
            )
            if mark_opened:
                fronter._call.finish_bot_playback()
                await fronter._start_telephony_keepalive()
            _event(f"=== {label} sent direct bulk media (~{duration_ms}ms) ===")
            return True"""

new_tail = """            duration_ms = await send_direct_bulk_pcm(
                _ws_send_json,
                pcm,
                sample_rate=TELEPHONY_PIPELINE_RATE,
                encoding=bulk_encoding,
            )
            if mark_opened:
                await fronter.on_direct_greeting_complete()
                _event("=== greeting done — caller turn open (pending STT flushed) ===")
            _event(f"=== {label} sent direct bulk media (~{duration_ms}ms) ===")
            return True"""

if old_tail in vtext:
    vtext = vtext.replace(old_tail, new_tail, 1)
elif "on_direct_greeting_complete" not in vtext:
    raise SystemExit("vicidial_session greeting tail not found")

old_fail = """            if not pcm:
                if mark_opened:
                    fronter._opened = False
                _event(f"=== {label}: no greeting PCM ===")
                return False"""

new_fail = """            if not pcm:
                if mark_opened:
                    fronter._opened = False
                    fronter._call.finish_bot_playback()
                _event(f"=== {label}: no greeting PCM ===")
                return False"""

if old_fail in vtext and "finish_bot_playback()" not in vtext.split("no greeting PCM")[0][-120:]:
    vtext = vtext.replace(old_fail, new_fail, 1)

vs.write_text(vtext, encoding="utf-8")
print("Patched pipeline.py and vicidial_session.py")
