"""Per-bot HTTP + WebSocket server for ViciDial media bridge."""

from __future__ import annotations

import os
import threading

import uvicorn
from fastapi import FastAPI, WebSocket
from loguru import logger

import httpx

from .bot_context import BotRunContext
from .inference_client import inference_pool_url
from .vicidial_session import call_runner_ready, run_vicidial_call


def inference_pool_error() -> str | None:
    """None when no pool is configured or it reports Whisper + Chatterbox loaded."""
    url = inference_pool_url()
    if not url:
        return None
    try:
        body = httpx.get(f"{url.rstrip('/')}/health", timeout=2.0).json()
    except Exception as exc:
        return f"inference pool unreachable: {exc}"
    if not body.get("ok") or not body.get("whisper_loaded"):
        return f"inference pool not loaded: {body.get('error') or 'warming'}"
    return None


def create_worker_app(ctx: BotRunContext) -> FastAPI:
    app = FastAPI(title=f"AI Fronter — {ctx.bot_name}", version="1.0")

    @app.get("/health")
    def health() -> dict[str, str | int | None | bool]:
        ready = call_runner_ready()
        pool_error = inference_pool_error()
        if pool_error:
            ready = False
        return {
            "ok": "true",
            "ready": ready,
            "pool_error": pool_error,
            "bot_id": ctx.bot_id,
            "agent_user": ctx.agent_user,
            "vicidial_campaign_id": ctx.vicidial_campaign_id,
        }

    @app.websocket("/ws")
    async def media_ws(websocket: WebSocket) -> None:
        await run_vicidial_call(websocket, ctx)

    return app


def start_worker_server(ctx: BotRunContext) -> tuple[threading.Thread, int]:
    port = int(os.getenv("FLEET_WORKER_MEDIA_PORT", "8800") or "8800")
    host = os.getenv("FLEET_WORKER_HOST", "0.0.0.0")
    app = create_worker_app(ctx)

    def _run() -> None:
        uvicorn.run(app, host=host, port=port, log_level="info")

    thread = threading.Thread(target=_run, name=f"media-{ctx.bot_id}", daemon=True)
    thread.start()
    logger.info(
        f"Media server for {ctx.bot_name} (agent {ctx.agent_user}) "
        f"on {host}:{port}/ws (FLEET_WORKER_MEDIA_PORT={port})"
    )
    return thread, port
