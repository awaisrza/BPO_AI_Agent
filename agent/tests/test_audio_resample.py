from app.audio_resample import normalize_pcm16, resample_pcm16


def test_resample_identity():
    pcm = b"\x00\x01" * 100
    assert resample_pcm16(pcm, 16000, 16000) == pcm


def test_normalize_quiet_audio():
    quiet = b"\x00\x10" * 200
    loud = normalize_pcm16(quiet)
    assert loud != quiet
