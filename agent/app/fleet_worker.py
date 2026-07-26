"""Fleet worker — loads a bot's script, pre-warms GPU models, sends heartbeats to Supabase."""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys

import httpx
from loguru import logger

from .config import settings
from .supabase_scripts import ScriptLoadError, load_script_for_bot


def _supabase_headers() -> dict[str, str]:
    return {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
    }


def _patch_bot_status(bot_id: str, status: str) -> None:
    base = settings.supabase_url.rstrip("/")
    url = f"{base}/rest/v1/bots"
    params = {"id": f"eq.{bot_id}"}
    with httpx.Client(timeout=15.0) as client:
        resp = client.patch(
            url,
            params=params,
            headers={**_supabase_headers(), "Prefer": "return=minimal"},
            json={"status": status},
        )
        resp.raise_for_status()


async def run_fleet_worker(bot_id: str) -> None:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise SystemExit("Fleet worker needs NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")

    try:
        script, agent_user = load_script_for_bot(bot_id)
    except ScriptLoadError as exc:
        raise SystemExit(str(exc)) from exc

    logger.info(f"Fleet worker starting for bot {agent_user} ({bot_id})")

    from .chatterbox_tts import TELEPHONY_PIPELINE_RATE
    from .pipeline import prewarm_voice_stack

    prewarm_voice_stack(script, sample_rate=TELEPHONY_PIPELINE_RATE, telephony=True)
    logger.info("Voice stack pre-warmed — agent ready for calls")

    _patch_bot_status(bot_id, "idle")

    stop = asyncio.Event()

    def _handle_signal(*_args: object) -> None:
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(ValueError):
            signal.signal(sig, _handle_signal)

    heartbeat_sec = int(os.getenv("FLEET_HEARTBEAT_SEC", "30") or "30")

    try:
        while not stop.is_set():
            try:
                _patch_bot_status(bot_id, "idle")
            except Exception as exc:
                logger.warning(f"Heartbeat failed: {exc}")
            try:
                await asyncio.wait_for(stop.wait(), timeout=heartbeat_sec)
            except asyncio.TimeoutError:
                continue
    finally:
        try:
            _patch_bot_status(bot_id, "offline")
        except Exception:
            pass
        logger.info(f"Fleet worker stopped for {agent_user}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m app.fleet_worker BOT_UUID", file=sys.stderr)
        sys.exit(1)
    asyncio.run(run_fleet_worker(sys.argv[1].strip()))
