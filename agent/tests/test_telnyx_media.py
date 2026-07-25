import pytest

from app.speech_renderer import UtteranceFlushFrame
from app.telnyx_media import (
    TelnyxBulkMediaProcessor,
    _is_silence_pcm,
    _KEEPALIVE_FLUSH_PCM_BYTES,
    pcm_to_telnyx_media_json,
)

try:
    from pipecat.frames.frames import BotStoppedSpeakingFrame, TTSAudioRawFrame
    from pipecat.processors.frame_processor import FrameDirection

    PIPECAT_AVAILABLE = True
except Exception:
    PIPECAT_AVAILABLE = False


def test_pcm_to_telnyx_media_json_pcmu():
    # 100 ms silence @ 8 kHz
    pcm = b"\x00\x00" * 800
    msg = pcm_to_telnyx_media_json(pcm, sample_rate=8000, encoding="PCMU")
    assert msg is not None
    assert '"event": "media"' in msg


def test_keepalive_threshold():
    pcm = b"\x00\x00" * (_KEEPALIVE_FLUSH_PCM_BYTES - 1)
    assert _is_silence_pcm(pcm)
    pcm2 = b"\x00\x00" * _KEEPALIVE_FLUSH_PCM_BYTES
    assert _is_silence_pcm(pcm2)


@pytest.mark.skipif(not PIPECAT_AVAILABLE, reason="pipecat not installed")
@pytest.mark.asyncio
async def test_bulk_media_emits_bot_stopped_after_final_flush():
    sent: list[str] = []
    upstream: list[object] = []

    async def _send_json(payload: str) -> None:
        sent.append(payload)

    processor = TelnyxBulkMediaProcessor(send_json=_send_json, encoding="PCMU")

    async def _spy_push(frame, direction=FrameDirection.DOWNSTREAM):  # type: ignore[no-untyped-def]
        if direction == FrameDirection.UPSTREAM:
            upstream.append(frame)

    processor.push_frame = _spy_push  # type: ignore[method-assign]

    pcm = b"\x01\x00" * 400  # 100 ms @ 8 kHz
    await processor.process_frame(
        TTSAudioRawFrame(audio=pcm, sample_rate=8000, num_channels=1),
        FrameDirection.DOWNSTREAM,
    )
    await processor.process_frame(
        UtteranceFlushFrame(final=True),
        FrameDirection.DOWNSTREAM,
    )

    assert sent, "bulk media should have been sent to Telnyx"
    assert any(isinstance(frame, BotStoppedSpeakingFrame) for frame in upstream)


@pytest.mark.skipif(not PIPECAT_AVAILABLE, reason="pipecat not installed")
@pytest.mark.asyncio
async def test_bulk_media_non_final_flush_does_not_emit_bot_stopped():
    sent: list[str] = []
    upstream: list[object] = []

    async def _send_json(payload: str) -> None:
        sent.append(payload)

    processor = TelnyxBulkMediaProcessor(send_json=_send_json, encoding="PCMU")

    async def _spy_push(frame, direction=FrameDirection.DOWNSTREAM):  # type: ignore[no-untyped-def]
        if direction == FrameDirection.UPSTREAM:
            upstream.append(frame)

    processor.push_frame = _spy_push  # type: ignore[method-assign]

    pcm = b"\x01\x00" * 400
    await processor.process_frame(
        TTSAudioRawFrame(audio=pcm, sample_rate=8000, num_channels=1),
        FrameDirection.DOWNSTREAM,
    )
    await processor.process_frame(
        UtteranceFlushFrame(final=False),
        FrameDirection.DOWNSTREAM,
    )

    assert sent
    assert not any(isinstance(frame, BotStoppedSpeakingFrame) for frame in upstream)
