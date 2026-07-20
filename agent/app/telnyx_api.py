"""Telnyx REST API helpers shared by the webhook server and the call session.

Kept in its own module (rather than telnyx_server.py) because telnyx_session.py
needs to call the hangup helper too, and telnyx_server.py already imports
telnyx_session.py — importing back the other way would be circular.
"""

from __future__ import annotations

import httpx
from loguru import logger

from .config import settings


def hangup_telnyx_call(call_control_id: str, *, timeout: float = 10.0) -> bool:
    """Force-terminate a live TeXML call via Telnyx's REST API.

    This is the piece that was missing: pushing ``EndFrame`` or closing our own
    WebSocket only tears down *our* side. Telnyx's TeXML keeps the PSTN leg open
    (falling through to ``<Pause length="120"/>``) until this call — or Telnyx's
    own ~2 minute pause timeout — actually ends it. Best-effort: never raises.
    """
    if not call_control_id:
        logger.warning("Telnyx hangup skipped: no call_control_id")
        return False
    if not settings.telnyx_account_sid or not settings.telnyx_api_key:
        logger.warning("Telnyx hangup skipped: missing TELNYX_ACCOUNT_SID/TELNYX_API_KEY")
        return False

    url = f"https://api.telnyx.com/v2/texml/Accounts/{settings.telnyx_account_sid}/Calls/{call_control_id}"
    headers = {
        "Authorization": f"Bearer {settings.telnyx_api_key}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, headers=headers, data={"Status": "completed"})
        if resp.status_code in (200, 202):
            logger.info(f"Telnyx hangup OK (call_sid={call_control_id}, status={resp.status_code})")
            return True
        if resp.status_code == 404:
            logger.info(
                f"Telnyx hangup skipped — call already ended "
                f"(call_sid={call_control_id}, status=404)"
            )
            return True
        logger.warning(
            f"Telnyx hangup failed (call_sid={call_control_id}) "
            f"status={resp.status_code} body={resp.text[:200]!r}"
        )
        return False
    except Exception as exc:  # noqa: BLE001 - best-effort, must never raise
        logger.warning(f"Telnyx hangup error (call_sid={call_control_id}): {exc}")
        return False
