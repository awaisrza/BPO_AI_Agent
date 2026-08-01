"""Per-bot HTTP + WebSocket server for ViciDial media bridge."""

from __future__ import annotations

import os
import threading

import uvicorn
from fastapi import FastAPI, WebSocket
from loguru import logger

from .bot_context import BotRunContext
from .vicidial_session import run_vicidial_call


def create_worker_app(ctx: BotRunContext) -> FastAPI:
    app = FastAPI(title=f"AI Fronter — {ctx.bot_name}", version="1.0")

    @app.get("/health")
    def health() -> dict[str, str | int | None]:
        return {
            "ok": "true",
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
    logger.info(f"Media server for {ctx.bot_name} (agent {ctx.agent_user}) on {host}:{port}/ws")
    return thread, port
