#!/usr/bin/env python3
"""Patch vicidial_session: voice_stack ready gate + immediate greeting on connect."""
from pathlib import Path

path = Path(__file__).resolve().parent.parent / "app" / "vicidial_session.py"
text = path.read_text(encoding="utf-8")

old_ready = '''_call_runner_lock = asyncio.Lock()
_IDLE_TIMEOUT_S = 120.0
_IDLE_CHECK_INTERVAL_S = 10.0
_GREETING_KICK_DELAY_S = 2.0


def _greeting_startup_timeout_s() -> float:
    return settings.telephony_greeting_startup_timeout_s


def call_runner_ready() -> bool:
    """True when the worker can accept a new ViciDial media WebSocket."""
    return not _call_runner_lock.locked()'''

new_ready = '''_call_runner_lock = asyncio.Lock()
_voice_stack_ready = False
_IDLE_TIMEOUT_S = 120.0
_IDLE_CHECK_INTERVAL_S = 10.0
_GREETING_KICK_DELAY_S = 2.0


def set_voice_stack_ready(ready: bool = True) -> None:
    global _voice_stack_ready
    _voice_stack_ready = ready


def _greeting_startup_timeout_s() -> float:
    return settings.telephony_greeting_startup_timeout_s


def call_runner_ready() -> bool:
    """True when prewarm finished and the worker can accept a new media WebSocket."""
    return _voice_stack_ready and not _call_runner_lock.locked()'''

if old_ready not in text:
    raise SystemExit("ready block not found")
text = text.replace(old_ready, new_ready, 1)

old_kick = '''        async def _ws_send_json(payload: str) -> None:
            await websocket.send_text(payload)

        async def _kick_greeting_if_stuck() -> None:
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

                _event("=== greeting kick failed: no cached greeting PCM ===")
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # noqa: BLE001
                _event(f"=== greeting kick failed: {exc} ===")

        @transport.event_handler("on_client_connected")
        async def on_client_connected(_transport, _client) -> None:
            nonlocal media_ready_at
            media_ready_at = time.monotonic()
            if fronter is not None and fronter._opened:
                fronter._touch_activity()
            _event("=== MEDIA READY — greeting should play within 1s ===")
            nonlocal greeting_kick_task
            greeting_kick_task = asyncio.create_task(_kick_greeting_if_stuck())'''

new_kick = '''        async def _ws_send_json(payload: str) -> None:
            await websocket.send_text(payload)

        async def _send_greeting_pcm(*, mark_opened: bool, label: str) -> bool:
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
            return True

        async def _play_immediate_greeting() -> None:
            """Play greeting as soon as media connects — bridge sync window is ~1–2s."""
            try:
                await _send_greeting_pcm(
                    mark_opened=True,
                    label="immediate greeting",
                )
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # noqa: BLE001
                _event(f"=== immediate greeting failed: {exc} ===")

        async def _kick_greeting_if_stuck() -> None:
            """Backup if immediate greeting did not run (StartFrame still stuck)."""
            try:
                await asyncio.sleep(_GREETING_KICK_DELAY_S)
                if shutdown.done or fronter is None or fronter._opened:
                    return
                _event(
                    f"=== StartFrame delayed >{_GREETING_KICK_DELAY_S:.0f}s — kicking greeting ==="
                )
                await _send_greeting_pcm(
                    mark_opened=True,
                    label="greeting kick",
                )
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # noqa: BLE001
                _event(f"=== greeting kick failed: {exc} ===")

        @transport.event_handler("on_client_connected")
        async def on_client_connected(_transport, _client) -> None:
            nonlocal media_ready_at
            media_ready_at = time.monotonic()
            if fronter is not None and fronter._opened:
                fronter._touch_activity()
            _event("=== MEDIA READY — greeting should play within 1s ===")
            nonlocal greeting_kick_task
            asyncio.create_task(_play_immediate_greeting())
            greeting_kick_task = asyncio.create_task(_kick_greeting_if_stuck())'''

if old_kick not in text:
    raise SystemExit("kick block not found")
text = text.replace(old_kick, new_kick, 1)
path.write_text(text, encoding="utf-8")
print(f"Patched {path}")
