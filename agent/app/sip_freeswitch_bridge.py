"""Bridge FreeSWITCH mod_audio_stream WebSocket ↔ GPU fleet worker."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os

from loguru import logger

from .freeswitch_adapter import (
    freeswitch_playback_from_telnyx,
    telnyx_media_from_l16,
)
from .sip_media_bridge import wait_worker_ready, worker_ws_url
from .sip_telephony import bootstrap_silence_messages, build_connected, build_start, new_stream_id


class _TelnyxWsShim:
    """Presents a Telnyx-shaped WS to bridge_to_worker while talking mod_audio_stream on the far side."""

    def __init__(self, fs_ws) -> None:
        self._fs = fs_ws
        self._inbound: asyncio.Queue[str | bytes | None] = asyncio.Queue()
        self._closed = False

    async def receive_text(self) -> str:
        while True:
            item = await self._inbound.get()
            if item is None:
                raise asyncio.CancelledError("FS shim closed")
            if isinstance(item, bytes):
                return telnyx_media_from_l16(item)
            return item

    async def send_text(self, message: str) -> None:
        playback = freeswitch_playback_from_telnyx(message)
        if playback is not None:
            await self._fs.send_text(playback)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self._closed = True
        await self._inbound.put(None)
        with contextlib.suppress(Exception):
            await self._fs.close(code=code, reason=reason)

    def feed_l16(self, chunk: bytes) -> None:
        if not self._closed:
            self._inbound.put_nowait(chunk)

    def feed_text(self, message: str) -> None:
        if not self._closed:
            self._inbound.put_nowait(message)


async def bridge_freeswitch_to_worker(
    fs_websocket,
    *,
    gpu_host: str,
    media_port: int,
    agent_user: str,
    org_id: str | None = None,
    caller: str = "",
    callee: str = "",
    vicidial_call_id: str = "",
) -> None:
    """Relay mod_audio_stream (L16 binary + streamAudio JSON) ↔ GPU Telnyx JSON."""
    import websockets

    if not await wait_worker_ready(gpu_host, media_port):
        raise TimeoutError(f"GPU worker not ready at {gpu_host}:{media_port}")

    target = worker_ws_url(gpu_host, media_port)
    stream_id = new_stream_id("fs")
    call_control_id = new_stream_id("call")
    shim = _TelnyxWsShim(fs_websocket)

    logger.info(
        f"FreeSWITCH bridge → {target} (org={org_id or 'legacy'}, agent={agent_user})"
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
        for msg in bootstrap_silence_messages(chunks=50):
            await gpu_ws.send(msg)

        stop = asyncio.Event()

        async def _fs_to_shim() -> None:
            try:
                while not stop.is_set():
                    message = await fs_websocket.receive()
                    if message["type"] == "websocket.disconnect":
                        break
                    if message["type"] == "websocket.receive":
                        data = message.get("bytes") or message.get("text")
                        if data is None:
                            continue
                        if isinstance(data, bytes):
                            shim.feed_l16(data)
                        else:
                            shim.feed_text(data)
            except Exception as exc:
                if not stop.is_set():
                    logger.debug(f"FS→shim relay ended: {exc}")
            finally:
                stop.set()
                await shim.close()

        async def _gpu_to_fs() -> None:
            try:
                async for message in gpu_ws:
                    if stop.is_set():
                        break
                    if isinstance(message, bytes):
                        message = message.decode("utf-8", errors="replace")
                    playback = freeswitch_playback_from_telnyx(message)
                    if playback is not None:
                        await fs_websocket.send_text(playback)
            except Exception as exc:
                if not stop.is_set():
                    logger.debug(f"GPU→FS relay ended: {exc}")
            finally:
                stop.set()

        async def _shim_to_gpu() -> None:
            try:
                while not stop.is_set():
                    telnyx_msg = await shim.receive_text()
                    await gpu_ws.send(telnyx_msg)
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                if not stop.is_set():
                    logger.debug(f"shim→GPU relay ended: {exc}")
            finally:
                stop.set()

        tasks = [
            asyncio.create_task(_fs_to_shim()),
            asyncio.create_task(_gpu_to_fs()),
            asyncio.create_task(_shim_to_gpu()),
        ]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        stop.set()
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            with contextlib.suppress(Exception):
                task.result()

    logger.info(f"FreeSWITCH bridge session ended (agent={agent_user})")
