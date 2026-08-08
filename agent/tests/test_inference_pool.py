"""Tests for shared inference pool client and adapters."""

from __future__ import annotations

import io
import wave

import pytest


def _make_wav(pcm: bytes, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


@pytest.fixture()
def pool_client(monkeypatch):
    monkeypatch.setenv("INFERENCE_POOL_URL", "http://pool.test:8780")

    async def _fake_transcribe(wav_bytes: bytes, *, no_speech_prob: float) -> str:
        return "hello there"

    async def _fake_synthesize(text: str, *, sample_rate: int, telephony: bool) -> bytes:
        return b"\x00\x01" * 160

    def _fake_warm(texts, *, sample_rate: int, telephony: bool):
        return {"warmed": len(texts), "cache_size": len(texts)}

    def _fake_health():
        return {"ok": True, "cache_size": 2}

    from app import inference_client as ic

    ic.get_inference_client.cache_clear()
    client = ic.InferenceClient("http://pool.test:8780")
    monkeypatch.setattr(client, "transcribe", _fake_transcribe)
    monkeypatch.setattr(client, "synthesize", _fake_synthesize)
    monkeypatch.setattr(client, "warm_cache_sync", _fake_warm)
    monkeypatch.setattr(client, "health_sync", _fake_health)
    monkeypatch.setattr(ic, "get_inference_client", lambda: client)
    return client


def test_inference_pool_enabled(monkeypatch):
    from app.inference_client import inference_pool_enabled

    monkeypatch.delenv("INFERENCE_POOL_URL", raising=False)
    assert not inference_pool_enabled()
    monkeypatch.setenv("INFERENCE_POOL_URL", "http://127.0.0.1:8780")
    assert inference_pool_enabled()


def test_build_stt_uses_pool_when_configured(monkeypatch, pool_client):
    monkeypatch.setenv("VOICE_BACKEND", "chatterbox")
    from app.pooled_stt import PooledWhisperSTTService
    from app.pipeline import _build_stt

    stt = _build_stt(telephony=True)
    assert isinstance(stt, PooledWhisperSTTService)


def test_build_tts_uses_pool_when_configured(monkeypatch, pool_client):
    monkeypatch.setenv("VOICE_BACKEND", "chatterbox")
    from app.config import ScriptConfig
    from app.pooled_tts import PooledChatterboxTTSService
    from app.pipeline import _build_tts

    tts = _build_tts(script=ScriptConfig(), sample_rate=16000, telephony=True)
    assert isinstance(tts, PooledChatterboxTTSService)


@pytest.mark.asyncio
async def test_pooled_stt_transcribes(pool_client):
    from app import pooled_stt
    from app.pooled_stt import PooledWhisperSTTService

    stt = PooledWhisperSTTService(no_speech_prob=0.65)
    stt._client = pool_client
    frames = []
    async for frame in stt.run_stt(_make_wav(b"\x00\x00" * 800)):
        frames.append(frame)
    assert len(frames) == 1
    assert getattr(frames[0], "text", "") == "hello there"


@pytest.mark.asyncio
async def test_pooled_tts_synthesizes(pool_client):
    from app.pooled_tts import PooledChatterboxTTSService

    tts = PooledChatterboxTTSService(sample_rate=16000)
    tts._client = pool_client
    audio_frames = []
    async for frame in tts.run_tts("Hi there", "ctx-1"):
        if frame is not None and hasattr(frame, "audio"):
            audio_frames.append(frame)
    assert audio_frames


@pytest.mark.asyncio
async def test_pool_transcribe_wav(monkeypatch):
    pytest.importorskip("fastapi")
    from app import inference_pool as ip

    class _FakeSegment:
        text = " hello"
        no_speech_prob = 0.1

    class _FakeWhisper:
        def transcribe(self, audio, language="en", vad_filter=False):
            return [_FakeSegment()], None

    ip._state.loaded = True
    ip._state.whisper_model = _FakeWhisper()
    text = await ip._transcribe_wav(_make_wav(b"\x00\x00" * 400), no_speech_prob=0.65)
    assert "hello" in text


@pytest.mark.asyncio
async def test_pool_synthesize_uses_cache(monkeypatch):
    pytest.importorskip("fastapi")
    from app import inference_pool as ip

    ip._state.pcm_cache["cached line"] = b"\x00\x01" * 8
    pcm = await ip._synthesize_line("cached line", sample_rate=16000, telephony=True)
    assert pcm == b"\x00\x01" * 8


def test_supervisor_status_includes_pool(monkeypatch):
    fastapi = pytest.importorskip("fastapi")
    assert fastapi  # silence unused in strict linters
    monkeypatch.setenv("INFERENCE_POOL_ENABLED", "true")
    from app.fleet_supervisor import FleetSupervisor

    sup = FleetSupervisor()
    body = sup.status()
    assert "inference_pool" in body
    assert body["inference_pool"]["enabled"] is True
