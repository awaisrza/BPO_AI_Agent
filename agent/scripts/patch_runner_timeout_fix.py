#!/usr/bin/env python3
"""Remove 3s runner join timeout that hangs up mid-greeting; fix greeting race."""
from __future__ import annotations

from pathlib import Path

p = Path(__file__).resolve().parents[1] / "app" / "vicidial_session.py"
text = p.read_text(encoding="utf-8")

new_tail = """        try:
            await runner_task
        except asyncio.CancelledError:
            pass
        finally:
            _event("=== pipeline worker finished ===")
            if shutdown is not None and not shutdown.done:
                end_reason = "runner_finished"
                await shutdown.end_call("runner_finished")
"""

try_start = text.find("        try:\n            await asyncio.wait_for(runner_task")
if try_start < 0:
    raise SystemExit("runner wait_for block not found")
try_end = text.find(
    '                await shutdown.end_call("runner_finished")\n',
    try_start,
)
if try_end < 0:
    raise SystemExit("runner_finished end_call not found")
try_end += len('                await shutdown.end_call("runner_finished")\n')
text = text[:try_start] + new_tail + text[try_end:]

old_send = """        async def _send_greeting_pcm(*, mark_opened: bool, label: str) -> bool:
            from .speech_renderer import CallState

            if shutdown.done or fronter is None or fronter._opened:
                return False

            opening = fronter._engine.open()
            tts_src = tts_for_cleanup or next(
                (p for p in pipeline.processors if getattr(p, "_cache", None) is not None),
                None,
            )
            pcm = None
            if tts_src is not None:
                pcm = greeting_pcm_from_cache(
                    tts_src,
                    opening.reply,
                    script_greeting=ctx.script.greeting,
                    telephony_max_words=settings.telephony_utterance_max_words,
                    greeting_single_chunk=settings.telephony_greeting_single_chunk,
                )
            if not pcm:
                _event(f"=== {label}: no greeting PCM ===")
                return False

            duration_ms = await send_direct_bulk_pcm(
                _ws_send_json,
                pcm,
                sample_rate=TELEPHONY_PIPELINE_RATE,
                encoding=bulk_encoding,
            )
            if mark_opened:
                fronter._opened = True
                fronter._touch_activity()
                fronter._call.state = CallState.LISTENING
            _event(f"=== {label} sent direct bulk media (~{duration_ms}ms) ===")
            return True"""

new_send = """        async def _send_greeting_pcm(*, mark_opened: bool, label: str) -> bool:
            from .speech_renderer import CallState

            if shutdown.done or fronter is None or fronter._opened:
                return False

            opening = fronter._engine.open()
            # Claim before send so StartFrame cannot race a second TTSSpeakFrame.
            if mark_opened:
                fronter._opened = True
                fronter._touch_activity()
                fronter._call.state = CallState.LISTENING

            tts_src = tts_for_cleanup or next(
                (p for p in pipeline.processors if getattr(p, "_cache", None) is not None),
                None,
            )
            pcm = None
            if tts_src is not None:
                pcm = greeting_pcm_from_cache(
                    tts_src,
                    opening.reply,
                    script_greeting=ctx.script.greeting,
                    telephony_max_words=settings.telephony_utterance_max_words,
                    greeting_single_chunk=settings.telephony_greeting_single_chunk,
                )
            if not pcm:
                if mark_opened:
                    fronter._opened = False
                _event(f"=== {label}: no greeting PCM ===")
                return False

            duration_ms = await send_direct_bulk_pcm(
                _ws_send_json,
                pcm,
                sample_rate=TELEPHONY_PIPELINE_RATE,
                encoding=bulk_encoding,
            )
            _event(f"=== {label} sent direct bulk media (~{duration_ms}ms) ===")
            return True"""

if old_send not in text:
    raise SystemExit("_send_greeting_pcm block not found")
text = text.replace(old_send, new_send, 1)
text = text.replace("_RUNNER_JOIN_TIMEOUT_S = 3.0\n\n", "")

p.write_text(text, encoding="utf-8")
print(f"Patched {p}")
