"""Telnyx Media Streams JSON helpers shared by SIP edge and lab AGI bridge."""

from __future__ import annotations

import base64
import json
import re
import uuid
from typing import Any

TELEPHONY_SAMPLE_RATE = 8000
ULAW_CHUNK_BYTES = 160
SLIN_CHUNK_BYTES = 320


def build_connected() -> dict[str, str]:
    return {"event": "connected", "version": "1.0.0"}


def build_start(
    *,
    stream_id: str,
    call_control_id: str,
    caller: str,
    callee: str,
    vicidial_call_id: str = "",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "event": "start",
        "sequence_number": "1",
        "stream_id": stream_id,
        "start": {
            "call_control_id": call_control_id,
            "from": caller or "unknown",
            "to": callee or "unknown",
            "media_format": {
                "encoding": "PCMU",
                "sample_rate": TELEPHONY_SAMPLE_RATE,
                "channels": 1,
            },
        },
    }
    vd_id = (vicidial_call_id or "").strip()
    if vd_id:
        payload["vicidial_call_id"] = vd_id
        payload["start"]["vicidial_call_id"] = vd_id
    return payload


def media_message(payload_b64: str) -> str:
    return json.dumps({"event": "media", "media": {"payload": payload_b64}})


def decode_media_payload(message: str) -> bytes | None:
    try:
        data = json.loads(message)
    except json.JSONDecodeError:
        return None
    if data.get("event") != "media":
        return None
    media = data.get("media") or {}
    payload_b64 = media.get("payload")
    if not payload_b64:
        return None
    try:
        return base64.b64decode(payload_b64)
    except Exception:
        return None


def ulaw_silence_chunk() -> bytes:
    return b"\xff" * ULAW_CHUNK_BYTES


def bootstrap_silence_messages(*, chunks: int = 50) -> list[str]:
    silence = base64.b64encode(ulaw_silence_chunk()).decode("ascii")
    return [media_message(silence) for _ in range(chunks)]


def new_stream_id(prefix: str = "sip") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify_org_name(name: str) -> str:
    slug = _SLUG_RE.sub("-", name.strip().lower()).strip("-")
    return slug or "org"


def parse_sip_user_host(sip_uri: str) -> tuple[str, str]:
    """Parse sip:6666@acme.bots.example.com → (6666, acme)."""
    raw = sip_uri.strip()
    if raw.lower().startswith("sip:"):
        raw = raw[4:]
    user, _, host = raw.partition("@")
    user = user.strip()
    host = host.strip().split(";")[0]
    subdomain = host.split(".")[0] if host else ""
    return user, subdomain


def build_sip_uri(
    agent_user: str,
    *,
    org_ref: str,
    domain: str,
) -> str:
    """Build sip:{agent}@{org_ref}.{domain} for ViciDial remote-agent config."""
    agent = agent_user.strip()
    org = org_ref.strip()
    base = domain.strip().lstrip(".")
    return f"sip:{agent}@{org}.{base}"
