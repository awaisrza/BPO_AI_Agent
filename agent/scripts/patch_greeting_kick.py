"""Patch greeting kick to send PCM via websocket directly."""
from __future__ import annotations

import re
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "app" / "vicidial_session.py"
text = p.read_text(encoding="utf-8")

old_anchor = """        bulk_media = next(
            (p for p in pipeline.processors if isinstance(p, TelnyxBulkMediaProcessor)),
            None,
        )

        async def _kick_greeting_if_stuck() -> None:"""

new_anchor = """        bulk_media = next(
            (p for p in pipeline.processors if isinstance(p, TelnyxBulkMediaProcessor)),
            None,
        )
        bulk_encoding = (
            bulk_media._encoding if bulk_media is not None else os.getenv("TELNYX_STREAM_CODEC", "PCMU")
        )

        async def _ws_send_json(payload: str) -> None:
            await websocket.send_text(payload)

        async def _kick_greeting_if_stuck() -> None:"""

if old_anchor not in text:
    raise SystemExit("anchor not found")
text = text.replace(old_anchor, new_anchor, 1)

pattern = re.compile(
    r'        async def _kick_greeting_if_stuck\(\) -> None:.*?'
    r'                _event\(\n'
    r'                    "=== greeting kick failed: no cached PCM or bulk media processor ==="\n'
    r'                \)',
    re.S,
)
new_kick = '''        async def _kick_greeting_if_stuck() -> None:
            """If StartFrame is slow, play cached greeting PCM directly on the media WS."""
            try:
                await asyncio.sleep(_GREETING_KICK_DELAY_S)
                if shutdown.done or fronter is None or fronter._opened:
                    return

                from .speech_renderer import CallState

                _event(
                    f"=== StartFrame delayed >{_GREETING_KICK_DELAY_S:.0f}s — kicking greeting ==="
                )
                opening = fronter._engine.open()
                fronter._opened = True
                fronter._touch_activity()
                fronter._call.state = CallState.LISTENING

                tts_src = tts_for_cleanup or next(
                    (p for p in pipeline.processors if getattr(p, "_cache", None)),
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
                if pcm:
                    duration_ms = await send_direct_bulk_pcm(
                        _ws_send_json,
                        pcm,
                        sample_rate=TELEPHONY_PIPELINE_RATE,
                        encoding=bulk_encoding,
                    )
                    _event(f"=== greeting kick sent direct bulk media (~{duration_ms}ms) ===")
                    return

                _event("=== greeting kick failed: no cached greeting PCM ===")'''

match = pattern.search(text)
if not match:
    raise SystemExit("kick block not found")
text = text[: match.start()] + new_kick + text[match.end() :]
p.write_bytes(text.encode("utf-8"))
print("patched", p)
