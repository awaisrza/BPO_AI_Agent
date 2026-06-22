"""Shared helpers for streaming ``SpokenChunkFrame`` through TTS services."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable

from loguru import logger

from .speech_renderer import SpokenChunkFrame, silence_pcm

try:
    from pipecat.frames.frames import Frame, TTSAudioRawFrame
    from pipecat.processors.frame_processor import FrameDirection
except Exception:  # pragma: no cover
    Frame = object  # type: ignore
    FrameDirection = object  # type: ignore


RunTTS = Callable[[str, str], AsyncGenerator[Frame | None, None]]


async def handle_spoken_chunk_frame(
    processor,
    frame: SpokenChunkFrame,
    direction: FrameDirection,
    *,
    run_tts: RunTTS,
) -> None:
    """Synthesize one chunk, stream audio, then optional pause silence."""
    text = frame.text.strip()
    context_id = processor.create_context_id()

    if text:
        logger.debug(f"TTS chunk: {text!r} (+{frame.pause_after_ms}ms pause)")
        async for audio_frame in run_tts(text, context_id):
            if audio_frame is not None:
                await processor.push_frame(audio_frame, direction)

    if frame.pause_after_ms > 0:
        pcm = silence_pcm(frame.pause_after_ms, processor.sample_rate)
        await processor.push_frame(
            TTSAudioRawFrame(
                audio=pcm,
                sample_rate=processor.sample_rate,
                num_channels=1,
            ),
            direction,
        )
