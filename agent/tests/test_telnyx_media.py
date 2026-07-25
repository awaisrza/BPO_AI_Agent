import audioop

from app.telnyx_media import pcm_to_telnyx_media_json, _is_silence_pcm, _KEEPALIVE_PCM_BYTES


def test_pcm_to_telnyx_media_json_pcmu():
    # 100 ms silence @ 8 kHz
    pcm = b"\x00\x00" * 800
    msg = pcm_to_telnyx_media_json(pcm, sample_rate=8000, encoding="PCMU")
    assert msg is not None
    assert '"event": "media"' in msg


def test_keepalive_threshold():
    pcm = b"\x00\x00" * (_KEEPALIVE_PCM_BYTES - 1)
    assert _is_silence_pcm(pcm)
    pcm2 = b"\x00\x00" * _KEEPALIVE_PCM_BYTES
    assert _is_silence_pcm(pcm2)
