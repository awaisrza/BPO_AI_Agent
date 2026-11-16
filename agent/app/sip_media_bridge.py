"""Bridge inbound SIP-edge WebSocket media to a GPU fleet worker /ws endpoint."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
from typing import Any

import httpx
from loguru import logger

from .sip_telephony import (
    bootstrap_silence_messages,
    build_connected,
    build_start,
    decode_media_payload,
    media_message,
    new_stream_id,
    ulaw_silence_chunk,
)


async def wait_worker_ready(
    gpu_host: str,
    media_port: int,
    *,
    timeout_sec: float = 20.0,
) -> bool:
    url = f"http://{gpu_host}:{media_port}/health"
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout_sec
    while loop.time() < deadline:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                body = resp.json()
            ready = body.get("ready", True)
            if ready is True or str(ready).lower() == "true":
                return True
            logger.debug(f"GPU worker busy (ready=false) at {url}")
        except Exception as exc:
            logger.debug(f"GPU health check failed ({url}): {exc}")
        await asyncio.sleep(0.5)
    return False


def worker_ws_url(gpu_host: str, media_port: int) -> str:
    scheme = os.getenv("GPU_WORKER_WS_SCHEME", "ws").strip() or "ws"
    return f"{scheme}://{gpu_host}:{media_port}/ws"


async def bridge_to_worker(
    inbound,
    *,
    gpu_host: str,
    media_port: int,
    agent_user: str,
    org_id: str | None = None,
    caller: str = "",
    callee: str = "",
    vicidial_call_id: str = "",
    bootstrap_chunks: int = 50,
) -> None:
    """Relay Telnyx-style JSON media between SIP edge WS and fleet worker WS."""
    import websockets

    if not await wait_worker_ready(gpu_host, media_port):
        raise TimeoutError(f"GPU worker not ready at {gpu_host}:{media_port}")

    target = worker_ws_url(gpu_host, media_port)
    stream_id = new_stream_id()
    call_control_id = new_stream_id("call")

    logger.info(
        f"SIP bridge connecting to worker {target} "
        f"(org={org_id or 'legacy'}, agent={agent_user})"
    )

    async with websockets.connect(
        target,
        open_timeout=float(os.getenv("SIP_EDGE_WS_TIMEOUT_SEC", "8") or "8"),
        ping_interval=20,
        ping_timeout=20,
        max_size=2**20,
    ) as gpu_ws:
        await gpu_ws.send(json.dumps(build_connected()))
        await gpu_ws.send(
            json.dumps(
                build_start(
                    stream_id=stream_id,
                    call_control_id=call_control_id,
                    caller=caller,
                    callee=callee or agent_user,
                    vicidial_call_id=vicidial_call_id,
                )
            )
        )
        for msg in bootstrap_silence_messages(chunks=bootstrap_chunks):
            await gpu_ws.send(msg)

        stop = asyncio.Event()

        async def _edge_to_gpu() -> None:
            try:
                while not stop.is_set():
                    message = await inbound.receive_text()
                    pcmu = decode_media_payload(message)
                    if pcmu is None:
                        if '"event"' in message and '"stop"' in message:
                            break
                        continue
                    await gpu_ws.send(media_message(base64.b64encode(pcmu).decode("ascii")))
            except Exception as exc:
                if not stop.is_set():
                    logger.debug(f"SIP edge→GPU relay ended: {exc}")
            finally:
                stop.set()

        async def _gpu_to_edge() -> None:
            try:
                async for message in gpu_ws:
                    if stop.is_set():
                        break
                    if isinstance(message, bytes):
                        message = message.decode("utf-8", errors="replace")
                    pcmu = decode_media_payload(message)
                    if pcmu is not None:
                        await inbound.send_text(message)
                    elif '"event"' in message and '"stop"' in message:
                        break
            except Exception as exc:
                if not stop.is_set():
                    logger.debug(f"GPU→SIP edge relay ended: {exc}")
            finally:
                stop.set()

        relay_tasks = [
            asyncio.create_task(_edge_to_gpu()),
            asyncio.create_task(_gpu_to_edge()),
        ]
        done, pending = await asyncio.wait(relay_tasks, return_when=asyncio.FIRST_COMPLETED)
        stop.set()
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            with contextlib.suppress(Exception):
                task.result()

    logger.info(f"SIP bridge session ended (agent={agent_user})")


async def bridge_pcmu_loop(
    send_pcmu: Any,
    recv_pcmu: Any,
    *,
    gpu_host: str,
    media_port: int,
    agent_user: str,
    org_id: str | None = None,
    caller: str = "",
    callee: str = "",
    vicidial_call_id: str = "",
) -> None:
    """Lower-level bridge for FreeSWITCH ESL/RTP adapters (callable hooks)."""
    import websockets

    if not await wait_worker_ready(gpu_host, media_port):
        raise TimeoutError(f"GPU worker not ready at {gpu_host}:{media_port}")

    target = worker_ws_url(gpu_host, media_port)
    stream_id = new_stream_id()
    call_control_id = new_stream_id("call")

    async with websockets.connect(target, open_timeout=8) as gpu_ws:
        await gpu_ws.send(json.dumps(build_connected()))
        await gpu_ws.send(
            json.dumps(
                build_start(
                    stream_id=stream_id,
                    call_control_id=call_control_id,
                    caller=caller,
                    callee=callee or agent_user,
                    vicidial_call_id=vicidial_call_id,
                )
            )
        )
        silence_b64 = base64.b64encode(ulaw_silence_chunk()).decode("ascii")
        for _ in range(50):
            await gpu_ws.send(media_message(silence_b64))

        stop = asyncio.Event()

        async def _in_to_gpu() -> None:
            while not stop.is_set():
                pcmu = await recv_pcmu()
                if not pcmu:
                    break
                await gpu_ws.send(media_message(base64.b64encode(pcmu).decode("ascii")))

        async def _gpu_to_out() -> None:
            async for message in gpu_ws:
                if stop.is_set():
                    break
                if isinstance(message, bytes):
                    message = message.decode("utf-8", errors="replace")
                pcmu = decode_media_payload(message)
                if pcmu is not None:
                    await send_pcmu(pcmu)

        t1 = asyncio.create_task(_in_to_gpu())
        t2 = asyncio.create_task(_gpu_to_out())
        await asyncio.wait({t1, t2}, return_when=asyncio.FIRST_COMPLETED)
        stop.set()
