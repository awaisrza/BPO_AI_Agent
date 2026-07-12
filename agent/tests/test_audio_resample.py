from app.audio_resample import enhance_for_telephony, normalize_pcm16, resample_pcm16


def test_resample_identity():
    pcm = b"\x00\x01" * 100
    assert resample_pcm16(pcm, 16000, 16000) == pcm


def test_normalize_quiet_audio():
    quiet = b"\x00\x10" * 200
    loud = normalize_pcm16(quiet)
    assert loud != quiet


def test_enhance_for_telephony():
    pcm = b"\x00\x10" * 200
    assert enhance_for_telephony(pcm) != pcm
