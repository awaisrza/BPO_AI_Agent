"""Convert between FreeSWITCH mod_audio_stream and Telnyx Media Streams JSON."""

from __future__ import annotations

import audioop
import base64
import json

from .sip_telephony import TELEPHONY_SAMPLE_RATE, decode_media_payload, media_message

_FS_PLAYBACK_TYPE = "streamAudio"


def l16_to_pcmu(l16: bytes, *, sample_width: int = 2) -> bytes:
    """FreeSWITCH mod_audio_stream sends 8 kHz signed-linear PCM."""
    if not l16:
        return b""
    return audioop.lin2ulaw(l16, sample_width)


def pcmu_to_l16(pcmu: bytes) -> bytes:
    if not pcmu:
        return b""
    return audioop.ulaw2lin(pcmu, 2)


def telnyx_media_from_l16(l16: bytes) -> str:
    pcmu = l16_to_pcmu(l16)
    return media_message(base64.b64encode(pcmu).decode("ascii"))


def telnyx_media_from_pcmu(pcmu: bytes) -> str:
    return media_message(base64.b64encode(pcmu).decode("ascii"))


def freeswitch_playback_json(pcmu: bytes, *, sample_rate: int = TELEPHONY_SAMPLE_RATE) -> str:
    """JSON response mod_audio_stream expects for inbound playback (v1.0.3+ STREAM_PLAYBACK)."""
    return json.dumps(
        {
            "type": _FS_PLAYBACK_TYPE,
            "data": {
                "audioDataType": "pcmu",
                "sampleRate": sample_rate,
                "audioData": base64.b64encode(pcmu).decode("ascii"),
            },
        }
    )


def freeswitch_playback_from_telnyx(message: str) -> str | None:
    pcmu = decode_media_payload(message)
    if pcmu is None:
        return None
    return freeswitch_playback_json(pcmu)


def is_freeswitch_playback_message(message: str) -> bool:
    try:
        data = json.loads(message)
    except json.JSONDecodeError:
        return False
    return data.get("type") == _FS_PLAYBACK_TYPE
