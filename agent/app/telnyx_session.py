"""Run the fronter pipeline on a Telnyx Media Streams WebSocket (real PSTN call)."""

from __future__ import annotations

import asyncio
import os
import time
import traceback
from pathlib import Path

from loguru import logger

from .chatterbox_tts import TELEPHONY_PIPELINE_RATE
from .config import ScriptConfig, settings
from .pipeline import build_pipeline

_CRASH_LOG = Path("/tmp/telnyx_events.log")
_active_call_ids: set[str] = set()
_completed_call_ids: dict[str, float] = {}
_session_lock = asyncio.Lock()
_COMPLETED_TTL_S = 120.0


def _prune_completed_calls() -> None:
    now = time.monotonic()
    stale = [key for key, ts in _completed_call_ids.items() if now - ts > _COMPLETED_TTL_S]
    for key in stale:
        _completed_call_ids.pop(key, None)


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
    session_key: str | None = None
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

        session_key = call_control_id or stream_id
        async with _session_lock:
            _prune_completed_calls()
            if session_key in _completed_call_ids:
                _event(f"=== WS REJECTED (call already ended {session_key}) ===")
                await websocket.close(code=1000)
                return
            if session_key in _active_call_ids:
                _event(f"=== DUPLICATE WS REJECTED (active call {session_key}) ===")
                await websocket.close(code=1000)
                return
            _active_call_ids.add(session_key)

        os.environ.setdefault("TELNYX_API_KEY", settings.telnyx_api_key or "")
        inbound_encoding = outbound_encoding
        _event(f"=== CODEC inbound={inbound_encoding} outbound={outbound_encoding} ===")

        serializer = TelnyxFrameSerializer(
            stream_id=stream_id,
            outbound_encoding=outbound_encoding,
            inbound_encoding=inbound_encoding,
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

        sample_rate = TELEPHONY_PIPELINE_RATE
        build_started = time.monotonic()
        _event(f"=== BUILDING PIPELINE (sample_rate={sample_rate}) ===")
        pipeline = build_pipeline(
            transport,
            agent_user=agent_user,
            script=script,
            mic_test=True,
            sample_rate=sample_rate,
            telephony=True,
        )
        _event(
            f"=== PIPELINE BUILT in {(time.monotonic() - build_started) * 1000:.0f}ms ==="
        )
        if (time.monotonic() - build_started) > 2.0:
            _event(
                "WARNING: pipeline build >2s — Telnyx may hang up before greeting. "
                "Ensure pre-warm finished and STT reuse log appears on connect."
            )
        tts_for_cleanup = pipeline.processors[-2] if pipeline.processors else None

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
            ms = (time.monotonic() - connect_started) * 1000
            _event(f"=== MEDIA READY — greeting should play within 1s (connect {ms:.0f}ms) ===")

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(_transport, _client) -> None:
            _event("=== CALL ENDED (remote hung up or stream closed) ===")
            if tts_for_cleanup is not None and hasattr(tts_for_cleanup, "cancel_background_work"):
                await tts_for_cleanup.cancel_background_work()
            await worker.cancel()

        connect_started = time.monotonic()
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
    finally:
        if session_key:
            async with _session_lock:
                _active_call_ids.discard(session_key)
                _completed_call_ids[session_key] = time.monotonic()
