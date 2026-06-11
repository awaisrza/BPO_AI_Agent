"""Custom Pipecat TTS service backed by the Fish Audio API.

Fish Audio is billed per UTF-8 byte ($15/1M bytes ≈ $0.021/min of speech), which makes it the cheap
managed TTS for the pilot. In production, swap this for a self-hosted Piper/Kokoro service and a
cache of pre-synthesized static script lines.
"""

from __future__ import annotations

from typing import AsyncGenerator

import httpx
from loguru import logger

try:
    from pipecat.frames.frames import (
        ErrorFrame,
        Frame,
        TTSAudioRawFrame,
        TTSStartedFrame,
        TTSStoppedFrame,
    )
    from pipecat.services.tts_service import TTSService
except Exception:  # pragma: no cover - import paths vary across Pipecat versions
    TTSService = object  # type: ignore
    Frame = object  # type: ignore


FISH_TTS_URL = "https://api.fish.audio/v1/tts"


class FishAudioTTSService(TTSService):
    """Streams PCM audio from Fish Audio. Sample rate defaults to 16k for telephony pipelines."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "s1",
        reference_id: str = "",
        sample_rate: int = 16000,
        **kwargs,
    ):
        super().__init__(sample_rate=sample_rate, **kwargs)
        self._api_key = api_key
        self._model = model
        self._reference_id = reference_id
        self._sample_rate = sample_rate
        self._client = httpx.AsyncClient(timeout=30.0)

    def can_generate_metrics(self) -> bool:
        return True

    async def run_tts(self, text: str) -> AsyncGenerator[Frame, None]:
        logger.debug(f"FishAudio TTS: {text!r}")
        payload = {
            "text": text,
            "format": "pcm",
            "sample_rate": self._sample_rate,
            "latency": "balanced",
        }
        if self._reference_id:
            payload["reference_id"] = self._reference_id

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "model": self._model,
        }

        try:
            await self.start_ttfb_metrics()
            yield TTSStartedFrame()
            async with self._client.stream(
                "POST", FISH_TTS_URL, json=payload, headers=headers
            ) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes():
                    if not chunk:
                        continue
                    await self.stop_ttfb_metrics()
                    yield TTSAudioRawFrame(
                        audio=chunk, sample_rate=self._sample_rate, num_channels=1
                    )
            yield TTSStoppedFrame()
        except Exception as exc:  # noqa: BLE001
            logger.error(f"FishAudio TTS error: {exc}")
            yield ErrorFrame(f"FishAudio TTS error: {exc}")

    async def stop(self, frame) -> None:  # type: ignore[override]
        await self._client.aclose()
        await super().stop(frame)
