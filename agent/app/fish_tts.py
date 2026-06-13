"""Custom Pipecat TTS service backed by the Fish Audio API.

Fish Audio is billed per UTF-8 byte ($15/1M bytes), which makes it a cheap managed TTS for the
pilot. In production, swap this for a self-hosted Piper/Kokoro service and a cache of
pre-synthesized static script lines.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
from loguru import logger

try:
    from pipecat.frames.frames import ErrorFrame, Frame, TTSAudioRawFrame
    from pipecat.services.settings import TTSSettings
    from pipecat.services.tts_service import TTSService
except Exception:  # pragma: no cover - import paths vary across Pipecat versions
    TTSService = object  # type: ignore
    Frame = object  # type: ignore
    TTSSettings = object  # type: ignore


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
        settings = TTSSettings(
            model=model,
            voice=reference_id or None,
            language=None,
        )
        super().__init__(
            sample_rate=sample_rate,
            push_start_frame=True,
            push_stop_frames=True,
            settings=settings,
            **kwargs,
        )
        self._api_key = api_key
        self._reference_id = reference_id
        self._client = httpx.AsyncClient(timeout=30.0)

    def can_generate_metrics(self) -> bool:
        return True

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
        logger.debug(f"FishAudio TTS: {text!r}")
        payload: dict = {
            "text": text,
            "format": "pcm",
            "sample_rate": self.sample_rate,
            "latency": "balanced",
        }
        if self._reference_id:
            payload["reference_id"] = self._reference_id

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "model": self._settings.model,
        }

        try:
            async with self._client.stream(
                "POST", FISH_TTS_URL, json=payload, headers=headers
            ) as resp:
                resp.raise_for_status()
                first_chunk = True
                async for chunk in resp.aiter_bytes():
                    if not chunk:
                        continue
                    if first_chunk:
                        await self.stop_ttfb_metrics()
                        first_chunk = False
                    yield TTSAudioRawFrame(
                        audio=chunk,
                        sample_rate=self.sample_rate,
                        num_channels=1,
                        context_id=context_id,
                    )
            await self.start_tts_usage_metrics(text)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"FishAudio TTS error: {exc}")
            yield ErrorFrame(f"FishAudio TTS error: {exc}")
        finally:
            await self.stop_ttfb_metrics()

    async def cleanup(self) -> None:
        await self._client.aclose()
        await super().cleanup()
