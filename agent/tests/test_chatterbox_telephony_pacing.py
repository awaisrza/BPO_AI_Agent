from app.chatterbox_tts import STREAM_FRAME_MS, TELEPHONY_PIPELINE_RATE, _chunk_pcm


def test_telephony_pipeline_rate_matches_pcmu():
    assert TELEPHONY_PIPELINE_RATE == 8000


def test_chunk_pcm_20ms_at_8khz():
    pcm = b"\x00\x01" * (TELEPHONY_PIPELINE_RATE * STREAM_FRAME_MS // 1000)
    chunks = list(_chunk_pcm(pcm, TELEPHONY_PIPELINE_RATE))
    assert len(chunks) == 1
    # 8000 Hz × 2 bytes × 20 ms / 1000 = 320 bytes per frame
    assert len(chunks[0]) == 320
