"""Shared GPU inference pool — one Whisper + one Chatterbox per host (Phase 3)."""

from __future__ import annotations

import asyncio
import io
import os
import wave
from contextlib import asynccontextmanager
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException, Query, Request
from loguru import logger
from pydantic import BaseModel, Field

from .chatterbox_paths import resolve_chatterbox_device, resolve_chatterbox_reference
from .chatterbox_tts import (
    TELEPHONY_PIPELINE_RATE,
    synthesize_pcm_sync,
    warm_chatterbox_cache_sync,
)
from .config import settings


class TTSRequest(BaseModel):
    text: str = Field(min_length=1)
    sample_rate: int = TELEPHONY_PIPELINE_RATE
    telephony: bool = False


class CacheWarmRequest(BaseModel):
    texts: list[str] = Field(default_factory=list)
    sample_rate: int = TELEPHONY_PIPELINE_RATE
    telephony: bool = False


class _PoolState:
    whisper_model: Any | None = None
    stt_lock: asyncio.Lock
    tts_lock: asyncio.Lock
    pcm_cache: dict[str, bytes]
    reference_path: Any
    device: str
    loaded: bool = False
    load_error: str | None = None

    def __init__(self) -> None:
        self.stt_lock = asyncio.Lock()
        self.tts_lock = asyncio.Lock()
        self.pcm_cache = {}
        self.reference_path = resolve_chatterbox_reference(
            settings.chatterbox_reference_audio or None
        )
        self.device = resolve_chatterbox_device(
            settings.chatterbox_device or settings.whisper_device or None
        )


_state = _PoolState()


def _load_whisper() -> Any:
    from faster_whisper import WhisperModel

    device = settings.whisper_device
    if device == "auto":
        import torch

        device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(
        f"Pool loading Whisper ({settings.whisper_model}, "
        f"device={device}, compute={settings.whisper_compute_type})"
    )
    return WhisperModel(
        settings.whisper_model,
        device=device,
        compute_type=settings.whisper_compute_type,
    )


def _warm_models() -> None:
    global _state
    try:
        _state.whisper_model = _load_whisper()
        # Chatterbox loads lazily on first TTS; touch reference path early.
        if not _state.reference_path.exists():
            raise FileNotFoundError(f"Chatterbox reference WAV missing: {_state.reference_path}")
        _state.loaded = True
        _state.load_error = None
        logger.info(f"Inference pool models ready (device={_state.device})")
    except Exception as exc:
        _state.loaded = False
        _state.load_error = str(exc)
        logger.error(f"Inference pool model load failed: {exc}")


def _wav_to_float32(wav_bytes: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        sample_rate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())
    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    return audio, sample_rate


async def _transcribe_wav(wav_bytes: bytes, *, no_speech_prob: float) -> str:
    if _state.whisper_model is None:
        raise RuntimeError("Whisper model not loaded")
    audio, _sample_rate = _wav_to_float32(wav_bytes)

    def _run() -> str:
        segments, _info = _state.whisper_model.transcribe(
            audio,
            language="en",
            vad_filter=False,
        )
        text = ""
        for segment in segments:
            if segment.no_speech_prob < no_speech_prob:
                text += f"{segment.text} "
        return text.strip()

    async with _state.stt_lock:
        return await asyncio.to_thread(_run)


async def _synthesize_line(
    text: str,
    *,
    sample_rate: int,
    telephony: bool,
) -> bytes:
    line = text.strip()
    if not line:
        return b""

    cached = _state.pcm_cache.get(line)
    if cached is not None:
        return cached

    async with _state.tts_lock:
        cached = _state.pcm_cache.get(line)
        if cached is not None:
            return cached
        pcm = await asyncio.to_thread(
            synthesize_pcm_sync,
            text=line,
            reference_path=_state.reference_path,
            device=_state.device,
            exaggeration=settings.chatterbox_exaggeration,
            cfg_weight=settings.chatterbox_cfg_weight,
            sample_rate=sample_rate,
            telephony=telephony,
        )
        _state.pcm_cache[line] = pcm
        return pcm


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    await asyncio.to_thread(_warm_models)
    yield


def build_app() -> FastAPI:
    app = FastAPI(title="AI Fronter Inference Pool", version="1.0", lifespan=_lifespan)

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "ok": _state.loaded,
            "error": _state.load_error,
            "whisper_loaded": _state.whisper_model is not None,
            "device": _state.device,
            "reference_audio": str(_state.reference_path),
            "cache_size": len(_state.pcm_cache),
        }

    @app.post("/v1/stt")
    async def stt_endpoint(
        request: Request,
        no_speech_prob: float = Query(default=0.65, ge=0.0, le=1.0),
    ) -> dict[str, str]:
        if not _state.loaded:
            raise HTTPException(status_code=503, detail=_state.load_error or "Pool not ready")
        wav_bytes = await request.body()
        if not wav_bytes:
            raise HTTPException(status_code=400, detail="Empty audio body")
        try:
            text = await _transcribe_wav(wav_bytes, no_speech_prob=no_speech_prob)
        except Exception as exc:
            logger.error(f"Pool STT failed: {exc}")
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"text": text}

    @app.post("/v1/tts")
    async def tts_endpoint(body: TTSRequest) -> Any:
        if not _state.loaded:
            raise HTTPException(status_code=503, detail=_state.load_error or "Pool not ready")
        try:
            pcm = await _synthesize_line(
                body.text,
                sample_rate=body.sample_rate,
                telephony=body.telephony,
            )
        except Exception as exc:
            logger.error(f"Pool TTS failed: {exc}")
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        from fastapi.responses import Response

        return Response(content=pcm, media_type="application/octet-stream")

    @app.post("/v1/cache/warm")
    async def cache_warm(body: CacheWarmRequest) -> dict[str, Any]:
        if not _state.loaded:
            raise HTTPException(status_code=503, detail=_state.load_error or "Pool not ready")

        missing = [
            t.strip()
            for t in body.texts
            if t.strip() and t.strip() not in _state.pcm_cache
        ]
        if not missing:
            return {
                "warmed": 0,
                "cache_size": len(_state.pcm_cache),
                "skipped": len(body.texts),
            }

        async with _state.tts_lock:
            before = len(_state.pcm_cache)

            def _warm() -> dict[str, bytes]:
                return warm_chatterbox_cache_sync(
                    texts=missing,
                    reference_path=_state.reference_path,
                    device=_state.device,
                    exaggeration=settings.chatterbox_exaggeration,
                    cfg_weight=settings.chatterbox_cfg_weight,
                    sample_rate=body.sample_rate,
                    telephony=body.telephony,
                )

            warmed = await asyncio.to_thread(_warm)
            _state.pcm_cache.update(warmed)

        return {
            "warmed": len(_state.pcm_cache) - before,
            "cache_size": len(_state.pcm_cache),
        }

    return app


def run_inference_pool(host: str | None = None, port: int | None = None) -> None:
    import uvicorn

    bind_host = host or os.getenv("INFERENCE_POOL_HOST", "127.0.0.1")
    bind_port = port or int(os.getenv("INFERENCE_POOL_PORT", "8780") or "8780")
    app = build_app()
    logger.info(f"Inference pool listening on {bind_host}:{bind_port}")
    uvicorn.run(app, host=bind_host, port=bind_port, log_level="info")


if __name__ == "__main__":
    run_inference_pool()
