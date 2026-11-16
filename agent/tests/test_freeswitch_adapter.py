"""FreeSWITCH mod_audio_stream adapter tests."""

from __future__ import annotations

import base64

from app.freeswitch_adapter import (
    freeswitch_playback_from_telnyx,
    l16_to_pcmu,
    pcmu_to_l16,
    telnyx_media_from_l16,
)


def test_l16_pcmu_roundtrip():
    silence_l16 = b"\x00\x00" * 160
    pcmu = l16_to_pcmu(silence_l16)
    assert len(pcmu) == 160
    back = pcmu_to_l16(pcmu)
    assert len(back) == len(silence_l16)


def test_telnyx_from_l16():
    msg = telnyx_media_from_l16(b"\x00\x00" * 80)
    assert '"event": "media"' in msg


def test_playback_from_telnyx():
    pcmu = b"\xff" * 160
    telnyx = __import__("app.sip_telephony", fromlist=["media_message"]).media_message(
        base64.b64encode(pcmu).decode("ascii")
    )
    fs_json = freeswitch_playback_from_telnyx(telnyx)
    assert fs_json is not None
    assert "streamAudio" in fs_json
    assert "pcmu" in fs_json
