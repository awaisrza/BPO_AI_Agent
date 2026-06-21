"""Pipecat TTS service backed by self-hosted Chatterbox Turbo (GPU)."""

from __future__ import annotations

import asyncio
import audioop
import threading
from collections.abc import AsyncGenerator, Iterable

from loguru import logger

from .chatterbox_paths import resolve_chatterbox_device, resolve_chatterbox_reference

try:
    from pipecat.frames.frames import ErrorFrame, Frame, TTSAudioRawFrame
    from pipecat.services.settings import TTSSettings
    from pipecat.services.tts_service import TTSService
except Exception:  # pragma: no cover
    TTSService = object  # type: ignore
    Frame = object  # type: ignore
    TTSSettings = object  # type: ignore


_model_lock = threading.Lock()
_shared_model = None
_shared_device: str | None = None


def _resample_pcm(pcm: bytes, src_rate: int, dst_rate: int) -> bytes:
    if src_rate == dst_rate or not pcm:
        return pcm
    converted, _ = audioop.ratecv(pcm, 2, 1, src_rate, dst_rate, None)
    return converted


def _chunk_pcm(pcm: bytes, chunk_bytes: int = 3200) -> Iterable[bytes]:
    for offset in range(0, len(pcm), chunk_bytes):
        yield pcm[offset : offset + chunk_bytes]


def _load_model(device: str):
    global _shared_model, _shared_device
    with _model_lock:
        if _shared_model is not None and _shared_device == device:
            return _shared_model
        from chatterbox.tts_turbo import ChatterboxTurboTTS

        logger.info(f"Loading Chatterbox Turbo on {device} (first run downloads weights)...")
        _shared_model = ChatterboxTurboTTS.from_pretrained(device=device)
        _shared_device = device
        logger.info(f"Chatterbox ready (sample_rate={_shared_model.sr})")
        return _shared_model


def _tensor_to_pcm16(wav, src_rate: int, dst_rate: int) -> bytes:
    import torch

    if wav.dim() > 1:
        wav = wav.squeeze(0)
    pcm = (
        wav.detach()
        .cpu()
        .float()
        .clamp(-1.0, 1.0)
        .mul(32767.0)
        .to(torch.int16)
        .numpy()
        .tobytes()
    )
    return _resample_pcm(pcm, src_rate, dst_rate)


def synthesize_pcm_sync(
    *,
    text: str,
    reference_path: Path,
    device: str,
    exaggeration: float,
    cfg_weight: float,
    sample_rate: int,
) -> bytes:
    model = _load_model(device)
    with _model_lock:
        wav = model.generate(
            text,
            audio_prompt_path=str(reference_path),
            exaggeration=exaggeration,
            cfg_weight=cfg_weight,
        )
    return _tensor_to_pcm16(wav, int(model.sr), sample_rate)


def warm_chatterbox_cache_sync(
    *,
    texts: Iterable[str],
    reference_path: Path,
    device: str,
    exaggeration: float,
    cfg_weight: float,
    sample_rate: int = 16000,
) -> dict[str, bytes]:
    cache: dict[str, bytes] = {}
    for text in texts:
        line = text.strip()
        if not line or line in cache:
            continue
        cache[line] = synthesize_pcm_sync(
            text=line,
            reference_path=reference_path,
            device=device,
            exaggeration=exaggeration,
            cfg_weight=cfg_weight,
            sample_rate=sample_rate,
        )
    return cache


class ChatterboxTTSService(TTSService):
    """Chatterbox Turbo with script-line cache and zero-shot voice clone."""

    def __init__(
        self,
        *,
        reference_audio: str | None = None,
        device: str | None = None,
        exaggeration: float = 0.35,
        cfg_weight: float = 0.5,
        sample_rate: int = 16000,
        cache: dict[str, bytes] | None = None,
        **kwargs,
    ):
        super().__init__(
            sample_rate=sample_rate,
            push_start_frame=True,
            push_stop_frames=True,
            settings=TTSSettings(model="chatterbox-turbo", voice=None, language=None),
            **kwargs,
        )
        self._reference = resolve_chatterbox_reference(reference_audio)
        self._device = resolve_chatterbox_device(device)
        self._exaggeration = exaggeration
        self._cfg_weight = cfg_weight
        self._cache = cache or {}
        self._infer_lock = asyncio.Lock()
        _load_model(self._device)

    def can_generate_metrics(self) -> bool:
        return True

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
        logger.debug(f"Chatterbox TTS: {text!r}")
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

            loop = asyncio.get_running_loop()
            async with self._infer_lock:
                pcm = await loop.run_in_executor(
                    None,
                    lambda: synthesize_pcm_sync(
                        text=text,
                        reference_path=self._reference,
                        device=self._device,
                        exaggeration=self._exaggeration,
                        cfg_weight=self._cfg_weight,
                        sample_rate=self.sample_rate,
                    ),
                )
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
            logger.error(f"Chatterbox TTS error: {exc}")
            yield ErrorFrame(f"Chatterbox TTS error: {exc}")
        finally:
            await self.stop_ttfb_metrics()
