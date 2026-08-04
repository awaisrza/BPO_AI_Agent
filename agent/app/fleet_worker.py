"""Fleet worker — ViciDial agent prep, media server, voice pre-warm, Supabase heartbeat."""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys

import httpx
from loguru import logger

from .supabase_client import ScriptLoadError, supabase_config, supabase_headers
from .supabase_scripts import load_bot_context
from .vicidial_worker_server import start_worker_server


def patch_bot_status(bot_id: str, status: str) -> None:
    base, key = supabase_config()
    url = f"{base}/rest/v1/bots"
    params = {"id": f"eq.{bot_id}"}
    with httpx.Client(timeout=15.0) as client:
        resp = client.patch(
            url,
            params=params,
            headers={
                **supabase_headers(key),
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json={"status": status},
        )
        resp.raise_for_status()


async def _prepare_vicidial(ctx) -> None:
    vici = ctx.vicidial_client()
    if not vici:
        logger.warning("No ViciDial client — skipping agent prep (set Integrations or .env)")
        return
    if not ctx.vicidial_campaign_id:
        logger.warning("No vicidial_campaign_id on campaign — agent may not receive hopper dials")
        return
    try:
        await vici.prepare_for_dialing(ctx.agent_user, ctx.vicidial_campaign_id)
        logger.info(
            f"ViciDial agent {ctx.agent_user} mapped to campaign {ctx.vicidial_campaign_id} — "
            "ensure BPO has campaign ACTIVE and leads in hopper"
        )
    except Exception as exc:
        logger.error(f"ViciDial prepare_for_dialing failed: {exc}")


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
    logger.info("Voice stack pre-warmed")

    await _prepare_vicidial(ctx)

    _media_thread, media_port = start_worker_server(ctx)
    logger.info(
        f"Ready for ViciDial audio at ws://0.0.0.0:{media_port}/ws "
        f"(point AGI bridge at GPU_IP:{media_port})"
    )

    if ctx.bot_id:
        patch_bot_status(ctx.bot_id, "idle")

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
                    await asyncio.to_thread(patch_bot_status, ctx.bot_id, "idle")
                except Exception as exc:
                    logger.warning(f"Heartbeat failed: {exc}")
            try:
                await asyncio.wait_for(stop.wait(), timeout=heartbeat_sec)
            except asyncio.TimeoutError:
                continue
    finally:
        if ctx.bot_id:
            with contextlib.suppress(Exception):
                patch_bot_status(ctx.bot_id, "offline")
        logger.info(f"Fleet worker stopped for {ctx.bot_name}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m app.fleet_worker BOT_UUID", file=sys.stderr)
        sys.exit(1)
    asyncio.run(run_fleet_worker(sys.argv[1].strip()))
