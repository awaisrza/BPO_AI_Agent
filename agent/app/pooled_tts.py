"""Chatterbox TTS adapter that delegates synthesis to the shared inference pool."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Iterable

from loguru import logger

from .chatterbox_tts import STREAM_FRAME_MS, TELEPHONY_PIPELINE_RATE
from .inference_client import get_inference_client
from .speech_renderer import (
    RtpKeepaliveStartFrame,
    RtpKeepaliveStopFrame,
    SpokenChunkFrame,
    iter_pcm_frames,
    silence_pcm,
)
from .tts_spoken_chunk import SpokenChunkTTSSupport, handle_spoken_chunk_frame

try:
    from pipecat.frames.frames import ErrorFrame, Frame, InterruptionFrame, TTSAudioRawFrame
    from pipecat.services.settings import TTSSettings
    from pipecat.services.tts_service import TTSService
except Exception:  # pragma: no cover
    TTSService = object  # type: ignore
    Frame = object  # type: ignore
    TTSSettings = object  # type: ignore


def _chunk_pcm(pcm: bytes, sample_rate: int = TELEPHONY_PIPELINE_RATE) -> Iterable[bytes]:
    chunk_bytes = max(2, sample_rate * 2 * STREAM_FRAME_MS // 1000)
    for offset in range(0, len(pcm), chunk_bytes):
        yield pcm[offset : offset + chunk_bytes]


class PooledChatterboxTTSService(SpokenChunkTTSSupport, TTSService):
    """Chatterbox-compatible TTS that uses the shared pool (no local GPU model load)."""

    def __init__(
        self,
        *,
        sample_rate: int = TELEPHONY_PIPELINE_RATE,
        cache: dict[str, bytes] | None = None,
        **kwargs,
    ):
        super().__init__(
            sample_rate=sample_rate,
            push_start_frame=True,
            push_stop_frames=True,
            settings=TTSSettings(model="chatterbox-turbo-pooled", voice=None, language=None),
            **kwargs,
        )
        self._telephony = sample_rate == TELEPHONY_PIPELINE_RATE
        self._cache = cache if cache is not None else {}
        self._client = get_inference_client()
        self._infer_lock = asyncio.Lock()
        self._prefetch_tasks: set[asyncio.Task] = set()
        self._keepalive_task: asyncio.Task | None = None
        self._keepalive_stop: asyncio.Event | None = None
        logger.info(
            f"TTS: pooled Chatterbox via {self._client._base} "
            f"(telephony={self._telephony}, local_cache={len(self._cache)})"
        )

    def clone_with_shared_cache(self) -> "PooledChatterboxTTSService":
        return PooledChatterboxTTSService(
            sample_rate=self.sample_rate,
            cache=self._cache,
        )

    async def cancel_background_work(self) -> None:
        self.cancel_speech()
        await self._stop_rtp_keepalive()
        for task in list(self._prefetch_tasks):
            task.cancel()
        self._prefetch_tasks.clear()

    async def _start_rtp_keepalive(self, direction) -> None:  # type: ignore[no-untyped-def]
        if not self._telephony:
            return
        if self._keepalive_task and not self._keepalive_task.done():
            return
        self._keepalive_stop = asyncio.Event()
        stop = self._keepalive_stop
        pcm = silence_pcm(STREAM_FRAME_MS, self.sample_rate)
        frames = list(iter_pcm_frames(pcm, self.sample_rate, frame_ms=STREAM_FRAME_MS))
        if not frames:
            return
        silent_frame = frames[0]

        async def _loop() -> None:
            while not stop.is_set():
                if self.speech_is_cancelled():
                    break
                await self.push_frame(
                    TTSAudioRawFrame(
                        audio=silent_frame,
                        sample_rate=self.sample_rate,
                        num_channels=1,
                    ),
                    direction,
                )
                try:
                    await asyncio.wait_for(stop.wait(), timeout=STREAM_FRAME_MS / 1000.0)
                    break
                except asyncio.TimeoutError:
                    continue

        self._keepalive_task = asyncio.create_task(_loop())

    async def _stop_rtp_keepalive(self) -> None:
        if self._keepalive_task is None:
            return
        if self._keepalive_stop is not None:
            self._keepalive_stop.set()
        task = self._keepalive_task
        self._keepalive_task = None
        self._keepalive_stop = None
        try:
            await asyncio.wait_for(task, timeout=1.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            task.cancel()

    async def _push_comfort_silence(self, direction) -> None:
        await self._start_rtp_keepalive(direction)

    async def prefetch_line(self, text: str) -> None:
        line = text.strip()
        if not line or line in self._cache:
            return
        try:
            async with self._infer_lock:
                if line in self._cache:
                    return
                pcm = await self._client.synthesize(
                    line,
                    sample_rate=self.sample_rate,
                    telephony=self._telephony,
                )
                self._cache[line] = pcm
                logger.debug(f"Pooled prefetch: {line[:48]!r}")
        except Exception as exc:
            logger.warning(f"Pooled prefetch failed ({line[:32]!r}…): {exc}")

    def _start_prefetch(self, text: str) -> None:
        if not text.strip():
            return
        task = asyncio.create_task(self.prefetch_line(text))
        self._prefetch_tasks.add(task)
        task.add_done_callback(self._prefetch_tasks.discard)

    def can_generate_metrics(self) -> bool:
        return True

    async def process_frame(self, frame, direction):  # type: ignore[override]
        if await self.handle_interruption_frame(frame, direction):
            await self._stop_rtp_keepalive()
            await super().process_frame(frame, direction)
            return
        if isinstance(frame, RtpKeepaliveStartFrame):
            await self._start_rtp_keepalive(direction)
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, RtpKeepaliveStopFrame):
            await self._stop_rtp_keepalive()
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, SpokenChunkFrame):
            if frame.prefetch_text:
                self._start_prefetch(frame.prefetch_text)
            await handle_spoken_chunk_frame(
                self,
                frame,
                direction,
                run_tts=self.run_tts,
            )
            return
        await super().process_frame(frame, direction)

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
        logger.debug(f"Pooled TTS: {text!r}")
        frame_pace_s = (STREAM_FRAME_MS / 1000.0) * 0.75 if self._telephony else 0.0
        line = text.strip()
        try:
            cached = self._cache.get(line)
            if cached is not None:
                logger.info(f"Pooled cache HIT: {line[:48]!r}")
            else:
                logger.info(f"Pooled cache MISS: {line[:48]!r}")
                async with self._infer_lock:
                    if self.speech_is_cancelled():
                        return
                    pcm = await self._client.synthesize(
                        line,
                        sample_rate=self.sample_rate,
                        telephony=self._telephony,
                    )
                    self._cache[line] = pcm
                    cached = pcm

            if cached is None or self.speech_is_cancelled():
                return

            await self.stop_ttfb_metrics()
            await self._stop_rtp_keepalive()
            for chunk in _chunk_pcm(cached, self.sample_rate):
                if self.speech_is_cancelled():
                    return
                yield TTSAudioRawFrame(
                    audio=chunk,
                    sample_rate=self.sample_rate,
                    num_channels=1,
                    context_id=context_id,
                )
                if frame_pace_s > 0:
                    await asyncio.sleep(frame_pace_s)
            await self.start_tts_usage_metrics(text)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Pooled TTS error: {exc}")
            yield ErrorFrame(f"Pooled TTS error: {exc}")
        finally:
            await self.stop_ttfb_metrics()
