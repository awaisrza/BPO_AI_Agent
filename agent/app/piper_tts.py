"""Pipecat TTS service backed by local Piper (self-hosted, cache-friendly)."""

from __future__ import annotations

import audioop
from collections.abc import AsyncGenerator, Iterable

from loguru import logger

from .piper_paths import (
    piper_model_sample_rate,
    resolve_piper_exe,
    resolve_piper_model,
    synthesize_pcm_async,
    synthesize_pcm_sync,
)
from .speech_renderer import SpokenChunkFrame
from .tts_spoken_chunk import handle_spoken_chunk_frame

try:
    from pipecat.frames.frames import ErrorFrame, Frame, TTSAudioRawFrame
    from pipecat.services.settings import TTSSettings
    from pipecat.services.tts_service import TTSService
except Exception:  # pragma: no cover
    TTSService = object  # type: ignore
    Frame = object  # type: ignore
    TTSSettings = object  # type: ignore


def _resample_pcm(pcm: bytes, src_rate: int, dst_rate: int) -> bytes:
    if src_rate == dst_rate or not pcm:
        return pcm
    converted, _ = audioop.ratecv(pcm, 2, 1, src_rate, dst_rate, None)
    return converted


def _chunk_pcm(pcm: bytes, chunk_bytes: int = 3200) -> Iterable[bytes]:
    for offset in range(0, len(pcm), chunk_bytes):
        yield pcm[offset : offset + chunk_bytes]


async def warm_piper_cache(
    *,
    texts: Iterable[str],
    piper_exe: str | None = None,
    model_path: str | None = None,
    speaker: int | None = None,
    sample_rate: int = 16000,
) -> dict[str, bytes]:
    """Pre-synthesize script lines so greeting/pitch/transfer play instantly."""
    exe = resolve_piper_exe(piper_exe)
    model = resolve_piper_model(model_path)
    model_rate = piper_model_sample_rate(model)
    cache: dict[str, bytes] = {}

    for text in texts:
        line = text.strip()
        if not line or line in cache:
            continue
        pcm = await synthesize_pcm_async(
            piper_exe=exe,
            model_path=model,
            text=line,
            speaker=speaker,
        )
        cache[line] = _resample_pcm(pcm, model_rate, sample_rate)

    return cache


def warm_piper_cache_sync(
    *,
    texts: Iterable[str],
    piper_exe: str | None = None,
    model_path: str | None = None,
    speaker: int | None = None,
    sample_rate: int = 16000,
) -> dict[str, bytes]:
    exe = resolve_piper_exe(piper_exe)
    model = resolve_piper_model(model_path)
    model_rate = piper_model_sample_rate(model)
    cache: dict[str, bytes] = {}

    for text in texts:
        line = text.strip()
        if not line or line in cache:
            continue
        pcm = synthesize_pcm_sync(
            piper_exe=exe,
            model_path=model,
            text=line,
            speaker=speaker,
        )
        cache[line] = _resample_pcm(pcm, model_rate, sample_rate)

    return cache


class PiperTTSService(TTSService):
    """Local Piper TTS with optional in-memory cache for static script lines."""

    def __init__(
        self,
        *,
        piper_exe: str | None = None,
        model_path: str | None = None,
        speaker: int | None = None,
        sample_rate: int = 16000,
        cache: dict[str, bytes] | None = None,
        **kwargs,
    ):
        super().__init__(
            sample_rate=sample_rate,
            push_start_frame=True,
            push_stop_frames=True,
            settings=TTSSettings(model="piper", voice=None, language=None),
            **kwargs,
        )
        self._piper_exe = resolve_piper_exe(piper_exe)
        self._model_path = resolve_piper_model(model_path)
        self._speaker = speaker
        self._model_rate = piper_model_sample_rate(self._model_path)
        self._cache = cache or {}

    def can_generate_metrics(self) -> bool:
        return True

    async def process_frame(self, frame, direction):  # type: ignore[override]
        if isinstance(frame, SpokenChunkFrame):
            await handle_spoken_chunk_frame(
                self,
                frame,
                direction,
                run_tts=self.run_tts,
            )
            return
        await super().process_frame(frame, direction)

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
        logger.debug(f"Piper TTS: {text!r}")
        try:
            cached = self._cache.get(text.strip())
            if cached is not None:
                await self.stop_ttfb_metrics()
                for chunk in _chunk_pcm(cached):
                    yield TTSAudioRawFrame(
                        audio=chunk,
                        sample_rate=self.sample_rate,
                        num_channels=1,
                        context_id=context_id,
                    )
                await self.start_tts_usage_metrics(text)
                return

            pcm = await synthesize_pcm_async(
                piper_exe=self._piper_exe,
                model_path=self._model_path,
                text=text,
                speaker=self._speaker,
            )
            pcm = _resample_pcm(pcm, self._model_rate, self.sample_rate)
            await self.stop_ttfb_metrics()
            for chunk in _chunk_pcm(pcm):
                yield TTSAudioRawFrame(
                    audio=chunk,
                    sample_rate=self.sample_rate,
                    num_channels=1,
                    context_id=context_id,
                )
            await self.start_tts_usage_metrics(text)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Piper TTS error: {exc}")
            yield ErrorFrame(f"Piper TTS error: {exc}")
        finally:
            await self.stop_ttfb_metrics()
