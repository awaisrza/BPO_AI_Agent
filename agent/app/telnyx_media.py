"""Telnyx bulk media — one PCMU WebSocket message per spoken line."""

from __future__ import annotations

import asyncio
import audioop
import base64
import json
import os
from collections.abc import Awaitable, Callable

from loguru import logger

from .chatterbox_tts import TELEPHONY_PIPELINE_RATE
from .speech_renderer import UtteranceFlushFrame

try:
    from pipecat.frames.frames import (
        BotStartedSpeakingFrame,
        BotStoppedSpeakingFrame,
        Frame,
        InterruptionFrame,
        TTSAudioRawFrame,
    )
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    PIPECAT_AVAILABLE = True
except Exception:  # pragma: no cover
    PIPECAT_AVAILABLE = False
    FrameProcessor = object  # type: ignore
    FrameDirection = object  # type: ignore
    Frame = object  # type: ignore
    InterruptionFrame = object  # type: ignore
    TTSAudioRawFrame = object  # type: ignore
    BotStartedSpeakingFrame = object  # type: ignore
    BotStoppedSpeakingFrame = object  # type: ignore

TELNYX_WIRE_RATE = 8000
# Batch RTP keepalive silence (~1 s) — not 20 ms per WS message.
_KEEPALIVE_FLUSH_PCM_BYTES = TELNYX_WIRE_RATE * 2

SendJson = Callable[[str], Awaitable[None]]


def telephony_bulk_media_enabled() -> bool:
    return os.getenv("TELNYX_BULK_MEDIA", "true").strip().lower() in ("1", "true", "yes")


def pcm_to_telnyx_media_json(
    pcm: bytes,
    *,
    sample_rate: int,
    encoding: str = "PCMU",
    wire_rate: int = TELNYX_WIRE_RATE,
) -> str | None:
    if not pcm:
        return None
    try:
        if sample_rate != wire_rate:
            pcm, _ = audioop.ratecv(pcm, 2, 1, sample_rate, wire_rate, None)
        if encoding == "PCMU":
            payload_bytes = audioop.lin2ulaw(pcm, 2)
        elif encoding == "PCMA":
            payload_bytes = audioop.lin2alaw(pcm, 2)
        else:
            logger.warning(f"Unsupported Telnyx encoding {encoding!r}")
            return None
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Telnyx media encode failed: {exc}")
        return None
    if not payload_bytes:
        return None
    duration_ms = len(pcm) * 1000 // (wire_rate * 2)
    log_fn = logger.debug if _is_silence_pcm(pcm) else logger.info
    log_fn(
        f"Telnyx bulk media: {len(payload_bytes)} bytes {encoding} (~{duration_ms} ms)"
    )
    payload = base64.b64encode(payload_bytes).decode("utf-8")
    return json.dumps({"event": "media", "media": {"payload": payload}})


def _is_silence_pcm(pcm: bytes) -> bool:
    if not pcm:
        return True
    return audioop.max(pcm, 2) == 0


def _playback_duration_ms(pcm: bytes, *, sample_rate: int, wire_rate: int) -> int:
    if not pcm:
        return 0
    if sample_rate != wire_rate:
        pcm, _ = audioop.ratecv(pcm, 2, 1, sample_rate, wire_rate, None)
    return len(pcm) * 1000 // (wire_rate * 2)



def greeting_pcm_from_cache(
    tts,
    greeting_text: str,
    *,
    script_greeting: str = "",
    telephony_max_words: int = 40,
    greeting_single_chunk: bool = False,
) -> bytes | None:
    """Resolve pre-warmed Chatterbox PCM for the opening greeting."""
    from .speech_renderer import (
        normalize_spoken_text,
        prepare_for_speech,
        render_speech_telephony,
    )

    cache = getattr(tts, "_cache", None)
    if cache is None:
        cache = {}

    prepared_script = prepare_for_speech(script_greeting) if script_greeting else ""
    norm_script = normalize_spoken_text(prepared_script)
    norm_greeting = normalize_spoken_text(greeting_text)

    if greeting_single_chunk and norm_script and norm_greeting == norm_script:
        for key in (norm_script.strip(), prepared_script.strip()):
            pcm = cache.get(key)
            if pcm:
                return pcm

    chunks = render_speech_telephony(greeting_text, max_words=telephony_max_words)
    parts: list[bytes] = []
    for chunk in chunks:
        line = chunk.text.strip()
        pcm = cache.get(line)
        if pcm is None:
            pcm = _synthesize_greeting_line(line)
            if pcm is not None and isinstance(cache, dict):
                cache[line] = pcm
        if pcm is None:
            return None
        parts.append(pcm)
    return b"".join(parts) if parts else None


def _synthesize_greeting_line(line: str) -> bytes | None:
    if not line.strip():
        return None
    try:
        from .inference_client import inference_pool_enabled, get_inference_client

        if inference_pool_enabled():
            return get_inference_client().synthesize_sync(
                line.strip(),
                sample_rate=TELEPHONY_PIPELINE_RATE,
                telephony=True,
            )
    except Exception as exc:
        logger.warning(f"Greeting pool synthesize failed ({line[:32]!r}): {exc}")
    return None


async def send_direct_bulk_pcm(
    send_json: SendJson,
    pcm: bytes,
    *,
    sample_rate: int = TELEPHONY_PIPELINE_RATE,
    encoding: str = "PCMU",
    wire_rate: int = TELNYX_WIRE_RATE,
) -> int:
    """Send one bot utterance on the Telnyx media WebSocket (bypasses pipecat)."""
    msg = pcm_to_telnyx_media_json(
        pcm,
        sample_rate=sample_rate,
        encoding=encoding,
        wire_rate=wire_rate,
    )
    if not msg:
        return 0
    await send_json(msg)
    duration_ms = _playback_duration_ms(
        pcm, sample_rate=sample_rate, wire_rate=wire_rate
    )
    if duration_ms > 0:
        await asyncio.sleep(duration_ms / 1000.0)
    return duration_ms



if PIPECAT_AVAILABLE:

    class TelnyxBulkMediaProcessor(FrameProcessor):  # type: ignore[misc]
        """Send each bot utterance as one Telnyx media message (not 20 ms WS frames)."""

        def __init__(
            self,
            *,
            send_json: SendJson,
            encoding: str = "PCMU",
            wire_rate: int = TELNYX_WIRE_RATE,
        ) -> None:
            super().__init__()
            self._send_json = send_json
            self._encoding = encoding
            self._wire_rate = wire_rate
            self._pcm = bytearray()
            self._rate = TELEPHONY_PIPELINE_RATE
            self._bot_speaking = False

        async def _ensure_bot_started(self) -> None:
            if self._bot_speaking:
                return
            self._bot_speaking = True
            await self.push_frame(BotStartedSpeakingFrame(), FrameDirection.UPSTREAM)

        async def _bot_finished_playback(self) -> None:
            if not self._bot_speaking:
                return
            self._bot_speaking = False
            logger.debug("Telnyx bulk media: bot playback finished — BotStoppedSpeaking")
            await self.push_frame(BotStoppedSpeakingFrame(), FrameDirection.UPSTREAM)

        async def _flush(self) -> tuple[int, bool]:
            if not self._pcm:
                return 0, True
            pcm = bytes(self._pcm)
            rate = self._rate
            is_silence = _is_silence_pcm(pcm)
            duration_ms = _playback_duration_ms(
                pcm, sample_rate=rate, wire_rate=self._wire_rate
            )
            if not is_silence:
                await self._ensure_bot_started()
            msg = pcm_to_telnyx_media_json(
                pcm,
                sample_rate=rate,
                encoding=self._encoding,
                wire_rate=self._wire_rate,
            )
            self._pcm.clear()
            if msg:
                await self._send_json(msg)
                if not is_silence:
                    from .call_trace import trace_call

                    trace_call(
                        f"=== bulk media sent (~{duration_ms}ms, {len(pcm)} pcm bytes) ==="
                    )
            return duration_ms, is_silence

        async def process_frame(self, frame, direction):  # type: ignore[no-untyped-def]
            await super().process_frame(frame, direction)

            if isinstance(frame, InterruptionFrame):
                self._pcm.clear()
                self._bot_speaking = False
                await self._send_json(json.dumps({"event": "clear"}))
                await self.push_frame(frame, direction)
                return

            if isinstance(frame, TTSAudioRawFrame):
                if frame.audio:
                    self._pcm.extend(frame.audio)
                    if frame.sample_rate:
                        self._rate = frame.sample_rate
                # Batch keepalive silence (~1 s) — avoids 20 ms WS floods + pipeline sleep.
                if (
                    _is_silence_pcm(bytes(self._pcm))
                    and len(self._pcm) >= _KEEPALIVE_FLUSH_PCM_BYTES
                ):
                    await self._flush()
                return

            if isinstance(frame, UtteranceFlushFrame):
                duration_ms, is_silence = await self._flush()
                if duration_ms > 0 and not is_silence:
                    await asyncio.sleep(duration_ms / 1000.0)
                if frame.final:
                    await self._bot_finished_playback()
                return

            await self.push_frame(frame, direction)
