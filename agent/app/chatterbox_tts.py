"""Pipecat TTS service backed by self-hosted Chatterbox Turbo (GPU)."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncGenerator, Iterable
from pathlib import Path

from loguru import logger

from .audio_resample import enhance_for_telephony, resample_pcm16
from .config import settings
from .chatterbox_paths import resolve_chatterbox_device, resolve_chatterbox_reference
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


_model_lock = threading.Lock()
_shared_model = None
_shared_device: str | None = None

# Telephony (Telnyx PCMU) is 8 kHz on the wire; run the pipeline at 16 kHz and let
# Pipecat's Telnyx serializer downsample once. Matches test_chatterbox.py clarity.
TELEPHONY_PIPELINE_RATE = 16000
# 20 ms frames — smoother Telnyx streaming (less perceived buffering).
STREAM_FRAME_MS = 20


def _chunk_pcm(pcm: bytes, sample_rate: int = TELEPHONY_PIPELINE_RATE) -> Iterable[bytes]:
    chunk_bytes = max(2, sample_rate * 2 * STREAM_FRAME_MS // 1000)
    for offset in range(0, len(pcm), chunk_bytes):
        yield pcm[offset : offset + chunk_bytes]


def _apply_chatterbox_dtype_patch(model) -> None:
    """Fix float64/float32 mismatches (numpy>=2 + librosa) in upstream chatterbox."""
    import types

    import numpy as np
    import torch

    tokenizer = getattr(getattr(model, "s3gen", None), "tokenizer", None)
    if tokenizer is not None and hasattr(tokenizer, "log_mel_spectrogram"):
        orig_mel = tokenizer.log_mel_spectrogram

        def patched_log_mel(self, audio, padding=0):
            if not torch.is_tensor(audio):
                audio = torch.from_numpy(np.asarray(audio, dtype=np.float32))
            else:
                audio = audio.float()
            return orig_mel(audio, padding)

        tokenizer.log_mel_spectrogram = types.MethodType(patched_log_mel, tokenizer)

    ve = getattr(model, "ve", None)
    if ve is not None and hasattr(ve, "embeds_from_wavs"):
        orig_embeds = ve.embeds_from_wavs

        def patched_embeds(wavs, sample_rate):
            fixed = [np.asarray(w, dtype=np.float32) for w in wavs]
            return orig_embeds(fixed, sample_rate)

        ve.embeds_from_wavs = patched_embeds

    if hasattr(model, "norm_loudness"):
        orig_norm = model.norm_loudness

        def patched_norm(self, wav, sr, target_lufs=-27):
            return orig_norm(np.asarray(wav, dtype=np.float32), sr, target_lufs)

        model.norm_loudness = types.MethodType(patched_norm, model)

    logger.debug("Applied Chatterbox dtype compatibility patch")


def _patch_perth_watermarker() -> None:
    """Chatterbox calls perth.PerthImplicitWatermarker(); PyPI perth often sets it to None."""
    try:
        import perth
    except ImportError:
        return

    cls = getattr(perth, "PerthImplicitWatermarker", None)
    if cls is not None and callable(cls):
        return

    class _NoOpWatermarker:
        def apply_watermark(self, wav, sample_rate):  # noqa: ANN001
            return wav

    perth.PerthImplicitWatermarker = _NoOpWatermarker
    logger.warning("Perth watermarker unavailable — using no-op stub (install Perth from GitHub for watermarking)")


def _load_model(device: str):
    global _shared_model, _shared_device
    with _model_lock:
        if _shared_model is not None and _shared_device == device:
            return _shared_model
        _patch_perth_watermarker()
        from chatterbox.tts_turbo import ChatterboxTurboTTS

        logger.info(f"Loading Chatterbox Turbo on {device} (first run downloads weights)...")
        _shared_model = ChatterboxTurboTTS.from_pretrained(device=device)
        _apply_chatterbox_dtype_patch(_shared_model)
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
    return resample_pcm16(pcm, src_rate, dst_rate)


def synthesize_pcm_sync(
    *,
    text: str,
    reference_path: Path,
    device: str,
    exaggeration: float,
    cfg_weight: float,
    sample_rate: int,
    telephony: bool = False,
) -> bytes:
    model = _load_model(device)
    if telephony:
        exaggeration = settings.telephony_chatterbox_exaggeration
        cfg_weight = settings.telephony_chatterbox_cfg_weight
    with _model_lock:
        wav = model.generate(
            text,
            audio_prompt_path=str(reference_path),
            exaggeration=exaggeration,
            cfg_weight=cfg_weight,
            norm_loudness=settings.chatterbox_norm_loudness,
        )
    pcm = _tensor_to_pcm16(wav, int(model.sr), sample_rate)
    return enhance_for_telephony(pcm) if telephony else pcm


def warm_chatterbox_cache_sync(
    *,
    texts: Iterable[str],
    reference_path: Path,
    device: str,
    exaggeration: float,
    cfg_weight: float,
    sample_rate: int = 16000,
    telephony: bool = False,
) -> dict[str, bytes]:
    cache: dict[str, bytes] = {}
    for text in texts:
        line = text.strip()
        if not line or line in cache:
            continue
        try:
            cache[line] = synthesize_pcm_sync(
                text=line,
                reference_path=reference_path,
                device=device,
                exaggeration=exaggeration,
                cfg_weight=cfg_weight,
                sample_rate=sample_rate,
                telephony=telephony,
            )
        except Exception as exc:
            logger.warning(f"Chatterbox cache skip ({line[:48]!r}…): {exc}")
    return cache


class ChatterboxTTSService(SpokenChunkTTSSupport, TTSService):
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
        self._telephony = sample_rate == TELEPHONY_PIPELINE_RATE
        self._cache = cache or {}
        self._infer_lock = asyncio.Lock()
        self._prefetch_tasks: set[asyncio.Task] = set()
        self._keepalive_task: asyncio.Task | None = None
        self._keepalive_stop: asyncio.Event | None = None
        _load_model(self._device)

    def clone_with_shared_cache(self) -> ChatterboxTTSService:
        """Fresh per-call instance so infer_lock/prefetch do not block the next call."""
        return ChatterboxTTSService(
            reference_audio=str(self._reference),
            device=self._device,
            exaggeration=self._exaggeration,
            cfg_weight=self._cfg_weight,
            sample_rate=self.sample_rate,
            cache=self._cache,
        )

    async def cancel_background_work(self) -> None:
        """Stop prefetch/synthesis so the next call's StartFrame is not blocked."""
        self.cancel_speech()
        await self._stop_rtp_keepalive()
        for task in list(self._prefetch_tasks):
            task.cancel()
        self._prefetch_tasks.clear()

    async def _start_rtp_keepalive(self, direction) -> None:  # type: ignore[no-untyped-def]
        """Stream 20 ms silence frames so Telnyx does not drop the call during gaps."""
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
            logger.debug("RTP keepalive started")
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
            logger.debug("RTP keepalive stopped")

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
        """Telnyx drops calls after ~3s with no outbound RTP — keepalive until speech starts."""
        await self._start_rtp_keepalive(direction)

    async def prefetch_line(self, text: str) -> None:
        """Synthesize upcoming speech while the caller hears the current line."""
        line = text.strip()
        if not line or line in self._cache:
            return
        loop = asyncio.get_running_loop()
        try:
            async with self._infer_lock:
                if line in self._cache:
                    return
                pcm = await loop.run_in_executor(
                    None,
                    lambda: synthesize_pcm_sync(
                        text=line,
                        reference_path=self._reference,
                        device=self._device,
                        exaggeration=self._exaggeration,
                        cfg_weight=self._cfg_weight,
                        sample_rate=self.sample_rate,
                        telephony=self._telephony,
                    ),
                )
                self._cache[line] = pcm
                logger.debug(f"Chatterbox prefetched: {line[:48]!r}")
        except Exception as exc:
            logger.warning(f"Chatterbox prefetch failed ({line[:32]!r}…): {exc}")

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
        logger.debug(f"Chatterbox TTS: {text!r}")
        frame_pace_s = (STREAM_FRAME_MS / 1000.0) * 0.75 if self._telephony else 0.0
        try:
            cached = self._cache.get(text.strip())
            if cached is not None:
                logger.info(f"Chatterbox cache HIT: {text[:48]!r}")
                await self.stop_ttfb_metrics()
                await self._stop_rtp_keepalive()
                # Pace telephony frames near realtime so Telnyx Media Streams
                # is not flooded (burst dumps often drop the WS mid-utterance).
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
                return

            loop = asyncio.get_running_loop()
            logger.info(f"Chatterbox cache MISS (GPU synth ~3-5s): {text[:48]!r}")
            async with self._infer_lock:
                if self.speech_is_cancelled():
                    return
                pcm = await loop.run_in_executor(
                    None,
                    lambda: synthesize_pcm_sync(
                        text=text,
                        reference_path=self._reference,
                        device=self._device,
                        exaggeration=self._exaggeration,
                        cfg_weight=self._cfg_weight,
                        sample_rate=self.sample_rate,
                        telephony=self._telephony,
                    ),
                )
            if self.speech_is_cancelled():
                return
            await self.stop_ttfb_metrics()
            await self._stop_rtp_keepalive()
            for chunk in _chunk_pcm(pcm, self.sample_rate):
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
            logger.error(f"Chatterbox TTS error: {exc}")
            yield ErrorFrame(f"Chatterbox TTS error: {exc}")
        finally:
            await self.stop_ttfb_metrics()
