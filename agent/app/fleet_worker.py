"""Fleet worker — loads bot context, pre-warms voice stack, heartbeats to Supabase."""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys

import httpx
from loguru import logger

from .config import settings
from .supabase_client import ScriptLoadError, supabase_config, supabase_headers
from .supabase_scripts import load_bot_context


def _patch_bot_status(bot_id: str, status: str) -> None:
    base, key = supabase_config()
    url = f"{base}/rest/v1/bots"
    params = {"id": f"eq.{bot_id}"}
    with httpx.Client(timeout=15.0) as client:
        resp = client.patch(
            url,
            params=params,
            headers={**supabase_headers(key), "Content-Type": "application/json", "Prefer": "return=minimal"},
            json={"status": status},
        )
        resp.raise_for_status()


async def run_fleet_worker(bot_id: str) -> None:
    try:
        ctx = load_bot_context(bot_id)
    except ScriptLoadError as exc:
        raise SystemExit(str(exc)) from exc

    logger.info(
        f"Fleet worker for {ctx.bot_name} "
        f"(ViciDial user={ctx.agent_user}, campaign={ctx.vicidial_campaign_id or 'unset'})"
    )

    from .chatterbox_tts import TELEPHONY_PIPELINE_RATE
    from .pipeline import prewarm_voice_stack

    prewarm_voice_stack(ctx.script, sample_rate=TELEPHONY_PIPELINE_RATE, telephony=True)
    logger.info("Voice stack pre-warmed — agent ready when ViciDial bridges a call")

    if ctx.bot_id:
        _patch_bot_status(ctx.bot_id, "idle")

    stop = asyncio.Event()

    def _handle_signal(*_args: object) -> None:
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(ValueError):
            signal.signal(sig, _handle_signal)

    heartbeat_sec = int(os.getenv("FLEET_HEARTBEAT_SEC", "30") or "30")

    try:
        while not stop.is_set():
            if ctx.bot_id:
                try:
                    _patch_bot_status(ctx.bot_id, "idle")
                except Exception as exc:
                    logger.warning(f"Heartbeat failed: {exc}")
            try:
                await asyncio.wait_for(stop.wait(), timeout=heartbeat_sec)
            except asyncio.TimeoutError:
                continue
    finally:
        if ctx.bot_id:
            with contextlib.suppress(Exception):
                _patch_bot_status(ctx.bot_id, "offline")
        logger.info(f"Fleet worker stopped for {ctx.bot_name}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m app.fleet_worker BOT_UUID", file=sys.stderr)
        sys.exit(1)
    asyncio.run(run_fleet_worker(sys.argv[1].strip()))
