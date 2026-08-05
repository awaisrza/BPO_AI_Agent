"""Run the fronter pipeline on a ViciDial media WebSocket (production calls).

Uses the same PCMU media JSON format as Telnyx Media Streams so the BPO AGI
bridge can forward RTP without custom codecs in the agent.
"""

from __future__ import annotations

import asyncio
import os
import time
import traceback
from pathlib import Path
from typing import Any

from loguru import logger

from .bot_context import BotRunContext
from .chatterbox_tts import TELEPHONY_PIPELINE_RATE
from .config import settings
from .pipeline import FronterProcessor, build_pipeline
from .telnyx_media import telephony_bulk_media_enabled

_CRASH_LOG = Path("/tmp/vicidial_events.log")
_active_sessions: set[str] = set()
_session_lock = asyncio.Lock()
_call_runner_lock = asyncio.Lock()
_IDLE_TIMEOUT_S = 120.0
_IDLE_CHECK_INTERVAL_S = 10.0


def _call_data_dict(call_data: Any) -> dict[str, Any]:
    """Pipecat may return TelnyxCallData (Pydantic) instead of a plain dict."""
    if isinstance(call_data, dict):
        return call_data
    model_dump = getattr(call_data, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    return {
        "stream_id": getattr(call_data, "stream_id", None),
        "call_control_id": getattr(call_data, "call_control_id", None),
        "call_id": getattr(call_data, "call_id", None),
        "outbound_encoding": getattr(call_data, "outbound_encoding", None),
    }


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


class _CallShutdown:
    def __init__(self, *, session_key: str, websocket) -> None:
        self._session_key = session_key
        self._websocket = websocket
        self._worker = None
        self._tts_for_cleanup = None
        self._done = False

    def attach(self, *, worker, tts_for_cleanup) -> None:
        self._worker = worker
        self._tts_for_cleanup = tts_for_cleanup

    @property
    def done(self) -> bool:
        return self._done

    async def end_call(self, reason: str) -> None:
        if self._done:
            return
        self._done = True
        _event(f"=== VICIDIAL END CALL (reason={reason}) ===")

        if self._tts_for_cleanup is not None and hasattr(self._tts_for_cleanup, "cancel_background_work"):
            try:
                await self._tts_for_cleanup.cancel_background_work()
            except Exception as exc:  # noqa: BLE001
                _event(f"shutdown: TTS cleanup failed: {exc}")

        if self._worker is not None:
            try:
                await self._worker.cancel()
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # noqa: BLE001
                _event(f"shutdown: worker cancel failed: {exc}")

        try:
            await self._websocket.close(code=1000)
        except Exception:
            pass


async def run_vicidial_call(websocket, ctx: BotRunContext) -> None:
    """Handle one live call bridged from ViciDial over WebSocket media."""
    # One PipelineWorker/runner at a time — concurrent WS sessions break greeting on call #2+.
    async with _call_runner_lock:
        await _run_vicidial_call_locked(websocket, ctx)


async def _run_vicidial_call_locked(websocket, ctx: BotRunContext) -> None:
    from pipecat.pipeline.worker import PipelineParams, PipelineWorker
    from pipecat.runner.utils import parse_telephony_websocket
    from pipecat.serializers.telnyx import TelnyxFrameSerializer
    from pipecat.transports.websocket.fastapi import (
        FastAPIWebsocketParams,
        FastAPIWebsocketTransport,
    )
    from pipecat.workers.runner import WorkerRunner

    _event(f"=== VICIDIAL WS handler bot={ctx.bot_name} agent={ctx.agent_user} ===")
    session_key: str | None = None
    shutdown: _CallShutdown | None = None
    idle_watchdog_task: asyncio.Task | None = None

    try:
        await websocket.accept()
        transport_type, call_data = await parse_telephony_websocket(websocket)
        cd = _call_data_dict(call_data)
        _event(f"=== parsed transport={transport_type} keys={list(cd.keys())} ===")

        stream_id = cd.get("stream_id") or f"vd-{ctx.agent_user}-{int(time.time())}"
        call_control_id = (
            cd.get("call_control_id")
            or cd.get("call_id")
            or stream_id
        )
        session_key = call_control_id

        async with _session_lock:
            if session_key in _active_sessions:
                _event(f"=== duplicate session rejected {session_key} ===")
                await websocket.close(code=1000)
                return
            _active_sessions.add(session_key)

        shutdown = _CallShutdown(session_key=session_key, websocket=websocket)

        encoding = cd.get("outbound_encoding") or "PCMU"
        serializer = TelnyxFrameSerializer(
            stream_id=stream_id,
            outbound_encoding=encoding,
            inbound_encoding="PCMU",
            call_control_id=call_control_id,
            api_key=settings.telnyx_api_key or "vicidial-bridge",
            params=TelnyxFrameSerializer.InputParams(
                auto_hang_up=False,
                sample_rate=TELEPHONY_PIPELINE_RATE,
                telnyx_sample_rate=8000,
                inbound_encoding="PCMU",
                outbound_encoding=encoding,
            ),
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

        async def _on_call_should_end(reason: str) -> None:
            await shutdown.end_call(reason)

        vici = ctx.vicidial_client()
        pipeline = build_pipeline(
            transport,
            agent_user=ctx.agent_user,
            script=ctx.script,
            mic_test=False,
            sample_rate=TELEPHONY_PIPELINE_RATE,
            telephony=True,
            vicidial_client=vici,
            on_call_should_end=_on_call_should_end,
            is_call_active=lambda: not shutdown.done,
        )

        tts_for_cleanup = pipeline.processors[-2] if pipeline.processors else None
        fronter = next((p for p in pipeline.processors if isinstance(p, FronterProcessor)), None)

        worker = PipelineWorker(
            pipeline,
            params=PipelineParams(
                audio_in_sample_rate=TELEPHONY_PIPELINE_RATE,
                audio_out_sample_rate=TELEPHONY_PIPELINE_RATE,
            ),
            enable_rtvi=False,
            idle_timeout_secs=None,
        )
        shutdown.attach(worker=worker, tts_for_cleanup=tts_for_cleanup)

        if ctx.bot_id:
            from .fleet_worker import patch_bot_status

            await asyncio.to_thread(patch_bot_status, ctx.bot_id, "live")

        async def _idle_watchdog() -> None:
            try:
                while True:
                    await asyncio.sleep(_IDLE_CHECK_INTERVAL_S)
                    if shutdown.done or fronter is None:
                        return
                    idle_for = time.monotonic() - fronter.last_activity_monotonic
                    if idle_for > _IDLE_TIMEOUT_S:
                        _event(f"=== idle timeout ({idle_for:.0f}s) ===")
                        await shutdown.end_call("idle_timeout")
                        return
            except asyncio.CancelledError:
                pass

        @transport.event_handler("on_client_connected")
        async def on_client_connected(_transport, _client) -> None:
            _event("=== MEDIA READY — greeting should play within 1s ===")

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(_transport, _client) -> None:
            await shutdown.end_call("remote_hangup")

        runner = WorkerRunner(handle_sigint=False)
        await runner.add_workers(worker)
        idle_watchdog_task = asyncio.create_task(_idle_watchdog())
        _event("=== pipeline worker running ===")
        try:
            await runner.run()
        finally:
            _event("=== pipeline worker finished ===")
            if not shutdown.done:
                await shutdown.end_call("runner_finished")
    except Exception:
        _event("=== VICIDIAL CRASH ===\n" + traceback.format_exc())
        if shutdown is not None:
            await shutdown.end_call("exception")
        raise
    finally:
        if idle_watchdog_task is not None:
            idle_watchdog_task.cancel()
        if session_key:
            async with _session_lock:
                _active_sessions.discard(session_key)
        if ctx.bot_id:
            from .fleet_worker import patch_bot_status

            await asyncio.to_thread(patch_bot_status, ctx.bot_id, "idle")
