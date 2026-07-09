"""Telnyx session with verbose logging — paste over app/telnyx_session.py on GPU."""

from __future__ import annotations

import json
import os

from loguru import logger

from .config import ScriptConfig, settings
from .pipeline import build_pipeline


async def _read_telnyx_handshake(websocket):
    """Read connected + start messages; return call_data dict."""
    first, second = {}, {}
    stream = websocket.iter_text()
    try:
        raw1 = await stream.__anext__()
        logger.info(f"TELNYX RAW[1]: {raw1[:400]}")
        first = json.loads(raw1) if raw1 else {}
    except StopAsyncIteration:
        raise RuntimeError("WebSocket closed before Telnyx connected message")
    try:
        raw2 = await stream.__anext__()
        logger.info(f"TELNYX RAW[2]: {raw2[:400]}")
        second = json.loads(raw2) if raw2 else {}
    except StopAsyncIteration:
        logger.warning("Only one Telnyx WebSocket message received")

    raw = second if second.get("stream_id") or second.get("start") else first
    start = raw.get("start") or {}
    call_data = {
        "stream_id": raw.get("stream_id"),
        "call_id": start.get("call_control_id"),
        "outbound_encoding": (start.get("media_format") or {}).get("encoding") or "PCMU",
        "from": start.get("from", "?"),
        "to": start.get("to", "?"),
    }
    logger.info(f"TELNYX PARSED: {call_data}")
    if not call_data["stream_id"]:
        raise RuntimeError(f"Missing stream_id in Telnyx handshake: {raw}")
    return call_data


async def run_telnyx_call(websocket, script: ScriptConfig, agent_user: str) -> None:
    from pipecat.pipeline.worker import PipelineParams, PipelineWorker
    from pipecat.serializers.telnyx import TelnyxFrameSerializer
    from pipecat.transports.websocket.fastapi import (
        FastAPIWebsocketParams,
        FastAPIWebsocketTransport,
    )
    from pipecat.workers.runner import WorkerRunner

    logger.info("=== TELNYX WS INCOMING ===")
    await websocket.accept()
    logger.info("=== TELNYX WS ACCEPTED ===")

    call_data = await _read_telnyx_handshake(websocket)
    stream_id = call_data["stream_id"]
    call_control_id = call_data.get("call_id")
    outbound_encoding = call_data.get("outbound_encoding") or "PCMU"

    os.environ.setdefault("TELNYX_API_KEY", settings.telnyx_api_key or "")

    serializer_params = TelnyxFrameSerializer.InputParams(auto_hang_up=False)
    serializer = TelnyxFrameSerializer(
        stream_id=stream_id,
        outbound_encoding=outbound_encoding,
        inbound_encoding="PCMU",
        call_control_id=call_control_id,
        api_key=settings.telnyx_api_key,
        params=serializer_params,
    )
    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
        ),
    )

    sample_rate = 8000
    logger.info("=== BUILDING PIPELINE ===")
    pipeline = build_pipeline(
        transport,
        agent_user=agent_user,
        script=script,
        mic_test=True,
        sample_rate=sample_rate,
    )
    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=sample_rate,
            audio_out_sample_rate=sample_rate,
        ),
        enable_rtvi=False,
        idle_timeout_secs=None,
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(_transport, _client) -> None:
        logger.info("=== TELNYX MEDIA READY — greeting should play ===")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(_transport, _client) -> None:
        logger.info("=== TELNYX CALL ENDED ===")
        await worker.cancel()

    logger.info("=== STARTING PIPELINE RUNNER ===")
    runner = WorkerRunner()
    await runner.add_workers(worker)
    await runner.run()
