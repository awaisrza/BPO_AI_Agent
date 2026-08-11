"""Whisper STT adapter that delegates transcription to the shared inference pool."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from loguru import logger

from .inference_client import get_inference_client

try:
    from pipecat.frames.frames import ErrorFrame, Frame, TranscriptionFrame
    from pipecat.services.stt_service import SegmentedSTTService
    from pipecat.utils.time import time_now_iso8601
except Exception:  # pragma: no cover
    SegmentedSTTService = object  # type: ignore
    Frame = object  # type: ignore


class PooledWhisperSTTService(SegmentedSTTService):
    """Segmented STT without loading Whisper locally — calls inference pool HTTP API."""

    def __init__(self, *, no_speech_prob: float = 0.65, sample_rate: int = 16000, **kwargs):
        from pipecat.services.whisper.stt import WhisperSTTService
        from pipecat.transcriptions.language import Language

        from .config import settings

        super().__init__(
            sample_rate=sample_rate,
            settings=WhisperSTTService.Settings(
                model=settings.whisper_model,
                language=Language.EN,
            ),
            **kwargs,
        )
        self._no_speech_prob = no_speech_prob
        self._client = get_inference_client()
        logger.info(
            f"STT: pooled Whisper via {self._client._base} "
            f"(no_speech_prob={no_speech_prob})"
        )

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
        await self.start_processing_metrics()
        try:
            text = await self._client.transcribe(audio, no_speech_prob=self._no_speech_prob)
        except Exception as exc:
            logger.error(f"Pooled STT error: {exc}")
            from .call_trace import trace_call

            trace_call(f"=== STT ERROR: {exc} ===")
            yield ErrorFrame(f"Pooled STT error: {exc}")
            return
        finally:
            await self.stop_processing_metrics()

        if text:
            logger.info(f"Pooled STT: {text[:64]!r}")
            from .call_trace import trace_call

            trace_call(f"=== STT heard: {text[:80]!r} ===")
        else:
            from .call_trace import trace_call

            trace_call("=== STT: (empty segment) ===")
            return

        yield TranscriptionFrame(
            text,
            self._user_id,
            time_now_iso8601(),
            None,
        )
