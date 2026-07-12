"""Shared helpers for streaming ``SpokenChunkFrame`` through TTS services."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable

from loguru import logger

from .speech_renderer import SpokenChunkFrame, silence_pcm

try:
    from pipecat.frames.frames import Frame, InterruptionFrame, TTSAudioRawFrame
    from pipecat.processors.frame_processor import FrameDirection
except Exception:  # pragma: no cover
    Frame = object  # type: ignore
    FrameDirection = object  # type: ignore
    InterruptionFrame = object  # type: ignore


RunTTS = Callable[[str, str], AsyncGenerator[Frame | None, None]]


class SpokenChunkTTSSupport:
    """Mixin: cancel queued chunk playback when the caller barges in."""

    _speech_cancelled: bool = False

    def reset_speech_cancellation(self) -> None:
        self._speech_cancelled = False

    def cancel_speech(self) -> None:
        self._speech_cancelled = True

    def speech_is_cancelled(self) -> bool:
        return self._speech_cancelled

    async def handle_interruption_frame(self, frame, direction) -> bool:  # type: ignore[no-untyped-def]
        if isinstance(frame, InterruptionFrame):
            self.cancel_speech()
            return True
        return False


async def handle_spoken_chunk_frame(
    processor,
    frame: SpokenChunkFrame,
    direction: FrameDirection,
    *,
    run_tts: RunTTS,
) -> None:
    """Synthesize one chunk, stream audio, then optional pause silence."""
    if getattr(processor, "speech_is_cancelled", lambda: False)():
        logger.debug(f"TTS chunk skipped (barge-in): {frame.text[:48]!r}")
        return

    if frame.reset_barge_in and hasattr(processor, "reset_speech_cancellation"):
        processor.reset_speech_cancellation()
        if getattr(processor, "_telephony", False) and hasattr(processor, "_push_comfort_silence"):
            await processor._push_comfort_silence(direction)

    if getattr(processor, "speech_is_cancelled", lambda: False)():
        return

    text = frame.text.strip()
    context_id = processor.create_context_id()

    if text:
        logger.debug(f"TTS chunk: {text!r} (+{frame.pause_after_ms}ms pause)")
        async for audio_frame in run_tts(text, context_id):
            if getattr(processor, "speech_is_cancelled", lambda: False)():
                logger.debug("TTS chunk playback stopped (barge-in)")
                break
            if audio_frame is not None:
                await processor.push_frame(audio_frame, direction)

    if frame.pause_after_ms > 0 and not getattr(processor, "speech_is_cancelled", lambda: False)():
        pcm = silence_pcm(frame.pause_after_ms, processor.sample_rate)
        await processor.push_frame(
            TTSAudioRawFrame(
                audio=pcm,
                sample_rate=processor.sample_rate,
                num_channels=1,
            ),
            direction,
        )
