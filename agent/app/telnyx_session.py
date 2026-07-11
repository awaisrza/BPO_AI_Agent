"""Run the fronter pipeline on a Telnyx Media Streams WebSocket (real PSTN call)."""

from __future__ import annotations

import os
import traceback
from pathlib import Path

from loguru import logger

from .config import ScriptConfig, settings
from .pipeline import build_pipeline

_CRASH_LOG = Path("/tmp/telnyx_events.log")


def _event(msg: str) -> None:
    line = msg.rstrip() + "\n"
    try:
        with _CRASH_LOG.open("a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
    except Exception:
        pass
    logger.info(line.strip())


async def run_telnyx_call(websocket, script: ScriptConfig, agent_user: str) -> None:
    """Handle one inbound or outbound Telnyx call over Media Streams."""
    from pipecat.pipeline.worker import PipelineParams, PipelineWorker
    from pipecat.runner.utils import parse_telephony_websocket
    from pipecat.serializers.telnyx import TelnyxFrameSerializer
    from pipecat.transports.websocket.fastapi import (
        FastAPIWebsocketParams,
        FastAPIWebsocketTransport,
    )
    from pipecat.workers.runner import WorkerRunner

    _event("=== WS HANDLER ENTERED ===")
    try:
        await websocket.accept()
        _event("=== WS ACCEPTED ===")

        transport_type, call_data = await parse_telephony_websocket(websocket)
        _event(f"=== PARSED type={transport_type} data={dict(call_data)} ===")

        if transport_type != "telnyx":
            raise RuntimeError(f"Expected telnyx, got {transport_type!r}")

        stream_id = call_data.get("stream_id")
        call_control_id = call_data.get("call_id")
        outbound_encoding = call_data.get("outbound_encoding") or "PCMU"
        if not stream_id:
            raise RuntimeError(f"Missing stream_id in handshake: {call_data}")

        os.environ.setdefault("TELNYX_API_KEY", settings.telnyx_api_key or "")

        serializer = TelnyxFrameSerializer(
            stream_id=stream_id,
            outbound_encoding=outbound_encoding,
            inbound_encoding="PCMU",
            call_control_id=call_control_id,
            api_key=settings.telnyx_api_key,
            params=TelnyxFrameSerializer.InputParams(auto_hang_up=False),
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
        _event("=== BUILDING PIPELINE ===")
        pipeline = build_pipeline(
            transport,
            agent_user=agent_user,
            script=script,
            mic_test=True,
            sample_rate=sample_rate,
        )

        worker_kwargs = {
            "params": PipelineParams(
                audio_in_sample_rate=sample_rate,
                audio_out_sample_rate=sample_rate,
            ),
        }
        try:
            worker = PipelineWorker(
                pipeline,
                enable_rtvi=False,
                idle_timeout_secs=None,
                **worker_kwargs,
            )
        except TypeError:
            _event("=== PipelineWorker fallback (no enable_rtvi/idle_timeout) ===")
            worker = PipelineWorker(pipeline, **worker_kwargs)

        @transport.event_handler("on_client_connected")
        async def on_client_connected(_transport, _client) -> None:
            _event("=== MEDIA READY — greeting should play ===")

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(_transport, _client) -> None:
            _event("=== CALL ENDED ===")
            await worker.cancel()

        _event("=== STARTING RUNNER ===")
        try:
            runner = WorkerRunner(handle_sigint=False)
        except TypeError:
            runner = WorkerRunner()
        await runner.add_workers(worker)
        await runner.run()
        _event("=== RUNNER FINISHED ===")
    except Exception:
        tb = traceback.format_exc()
        _event("=== CRASH ===\n" + tb)
        raise
