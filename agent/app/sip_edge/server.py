"""SIP edge control plane — routes SIP media to GPU fleet workers (production Phase 1)."""

from __future__ import annotations

import contextlib
import os

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from loguru import logger
from pydantic import BaseModel, Field

from .router import parse_inbound_sip_target, resolve_worker_route, sip_edge_domain
from ..sip_freeswitch_bridge import bridge_freeswitch_to_worker
from ..sip_media_bridge import bridge_to_worker
from ..sip_telephony import build_sip_uri, slugify_org_name


class RouteResponse(BaseModel):
    ok: bool
    error: str | None = None


class ConnectRequest(BaseModel):
    agent_user: str = Field(min_length=1)
    org_id: str | None = None
    org_slug: str | None = None
    sip_uri: str | None = None
    caller: str = ""
    callee: str = ""
    vicidial_call_id: str = ""


def build_app() -> FastAPI:
    app = FastAPI(title="AI Fronter SIP Edge", version="1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "domain": sip_edge_domain()}

    @app.get("/v1/route")
    def route(
        agent_user: str = Query(..., min_length=1),
        org_id: str | None = Query(default=None),
    ) -> dict:
        return resolve_worker_route(agent_user, org_id=org_id)

    @app.get("/v1/sip-uri")
    def sip_uri_template(
        agent_user: str = Query(..., min_length=1),
        org_id: str = Query(..., min_length=1),
        org_name: str | None = Query(default=None),
    ) -> dict[str, str]:
        org_ref = slugify_org_name(org_name) if org_name else org_id
        uri = build_sip_uri(agent_user, org_ref=org_ref, domain=sip_edge_domain())
        return {
            "sip_uri": uri,
            "domain": sip_edge_domain(),
            "org_ref": org_ref,
            "agent_user": agent_user.strip(),
            "note": "Point ViciDial remote agent external address at this SIP URI.",
        }

    @app.websocket("/v1/stream/fs")
    async def media_stream_freeswitch(
        websocket: WebSocket,
        agent_user: str = Query(..., min_length=1),
        org_id: str | None = Query(default=None),
        org_slug: str | None = Query(default=None),
        sip_uri: str | None = Query(default=None),
        caller: str = Query(default=""),
        callee: str = Query(default=""),
        vicidial_call_id: str = Query(default=""),
    ) -> None:
        """FreeSWITCH mod_audio_stream (L16 binary + streamAudio JSON) ↔ GPU worker."""
        await websocket.accept()
        try:
            user, resolved_org = parse_inbound_sip_target(
                sip_uri=sip_uri,
                agent_user=agent_user,
                org_id=org_id,
                org_slug=org_slug,
            )
            route = resolve_worker_route(user, org_id=resolved_org)
            if not route.get("ok"):
                await websocket.close(code=4404, reason=route.get("error") or "no worker")
                return
            gpu_host = str(route.get("gpu_host") or "127.0.0.1")
            media_port = int(route["media_port"])
            await bridge_freeswitch_to_worker(
                websocket,
                gpu_host=gpu_host,
                media_port=media_port,
                agent_user=user,
                org_id=resolved_org,
                caller=caller,
                callee=callee or user,
                vicidial_call_id=vicidial_call_id,
            )
        except WebSocketDisconnect:
            logger.info("FreeSWITCH stream disconnected")
        except Exception as exc:
            logger.error(f"FreeSWITCH stream failed: {exc}")
            with contextlib.suppress(Exception):
                await websocket.close(code=1011, reason=str(exc)[:120])

    @app.websocket("/v1/stream")
    async def media_stream(
        websocket: WebSocket,
        agent_user: str = Query(..., min_length=1),
        org_id: str | None = Query(default=None),
        org_slug: str | None = Query(default=None),
        sip_uri: str | None = Query(default=None),
        caller: str = Query(default=""),
        callee: str = Query(default=""),
        vicidial_call_id: str = Query(default=""),
    ) -> None:
        """FreeSWITCH mod_audio_stream (or test client) ↔ GPU worker bridge."""
        await websocket.accept()
        try:
            user, resolved_org = parse_inbound_sip_target(
                sip_uri=sip_uri,
                agent_user=agent_user,
                org_id=org_id,
                org_slug=org_slug,
            )
            route = resolve_worker_route(user, org_id=resolved_org)
            if not route.get("ok"):
                await websocket.close(code=4404, reason=route.get("error") or "no worker")
                return
            gpu_host = str(route.get("gpu_host") or "127.0.0.1")
            media_port = int(route["media_port"])
            await bridge_to_worker(
                websocket,
                gpu_host=gpu_host,
                media_port=media_port,
                agent_user=user,
                org_id=resolved_org,
                caller=caller,
                callee=callee or user,
                vicidial_call_id=vicidial_call_id,
            )
        except WebSocketDisconnect:
            logger.info("SIP edge client disconnected")
        except Exception as exc:
            logger.error(f"SIP edge stream failed: {exc}")
            with contextlib.suppress(Exception):
                await websocket.close(code=1011, reason=str(exc)[:120])

    return app


def run_sip_edge(host: str | None = None, port: int | None = None) -> None:
    import uvicorn

    bind_host = host or os.getenv("SIP_EDGE_HOST", "0.0.0.0")
    bind_port = port or int(os.getenv("SIP_EDGE_HTTP_PORT", "8790") or "8790")
    app = build_app()
    logger.info(
        f"SIP edge HTTP/WS on {bind_host}:{bind_port} "
        f"(domain={sip_edge_domain()}, codec=PCMU @ 8kHz)"
    )
    uvicorn.run(app, host=bind_host, port=bind_port, log_level="info")
