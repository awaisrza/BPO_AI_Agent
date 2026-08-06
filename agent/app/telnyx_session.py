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
from .pipeline import FronterProcessor, build_pipeline, tts_processor_for_cleanup
from .telnyx_api import hangup_telnyx_call
from .telnyx_media import telephony_bulk_media_enabled

_CRASH_LOG = Path("/tmp/telnyx_events.log")
_active_call_ids: set[str] = set()
_completed_call_ids: dict[str, float] = {}
_session_lock = asyncio.Lock()
_COMPLETED_TTL_S = 120.0
# How long the call can sit with no caller/bot activity before we assume the
# line is dead (e.g. a network partition ate the WebSocket close frame) and
# force it closed ourselves rather than leaving a silent zombie call.
_IDLE_TIMEOUT_S = 45.0
_IDLE_CHECK_INTERVAL_S = 10.0


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


_CALL_SHUTDOWN_CANCEL_S = 5.0


class _CallShutdown:
    """Single, idempotent teardown path for a Telnyx call.

    Every way a call can end — FSM hangup/transfer, the remote party hanging
    up, an unrecoverable exception, or an idle timeout — must funnel through
    ``end_call`` exactly once. Previously these paths were scattered and
    incomplete: a bot-initiated hangup never told Telnyx to actually end the
    PSTN leg, so the call sat open and silent (falling through TeXML's
    ``<Pause length="120"/>``) until the caller gave up or Telnyx's own ~2
    minute timeout fired.

    Ordering matters: the Telnyx REST hangup runs *first*, before touching the
    local worker/websocket, because cancelling our own worker from inside a
    frame it is currently processing can raise ``CancelledError`` partway
    through this method — we want the one step that actually ends the PSTN
    call to have already succeeded before that risk is taken.
    """

    def __init__(
        self,
        *,
        call_control_id: str | None,
        websocket,
        on_begin_shutdown=None,
    ) -> None:
        self._call_control_id = call_control_id
        self._websocket = websocket
        self._on_begin_shutdown = on_begin_shutdown
        self._worker = None
        self._tts_for_cleanup = None
        self._runner_task: asyncio.Task | None = None
        self._done = False

    def attach(
        self,
        *,
        worker,
        tts_for_cleanup,
        runner_task: asyncio.Task | None = None,
    ) -> None:
        self._worker = worker
        self._tts_for_cleanup = tts_for_cleanup
        self._runner_task = runner_task

    @property
    def done(self) -> bool:
        return self._done

    async def end_call(self, reason: str, *, hangup_telnyx: bool) -> None:
        if self._done:
            return
        self._done = True
        if self._on_begin_shutdown is not None:
            try:
                await self._on_begin_shutdown()
            except Exception as exc:  # noqa: BLE001
                _event(f"shutdown: session mark failed: {exc}")
        _event(f"=== ENDING CALL (reason={reason}) ===")

        if hangup_telnyx and self._call_control_id:
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, hangup_telnyx_call, self._call_control_id)
            except Exception as exc:  # noqa: BLE001
                _event(f"shutdown: telnyx hangup failed: {exc}")

        if self._runner_task is not None and not self._runner_task.done():
            self._runner_task.cancel()

        if self._tts_for_cleanup is not None and hasattr(self._tts_for_cleanup, "cancel_background_work"):
            try:
                await asyncio.wait_for(
                    self._tts_for_cleanup.cancel_background_work(),
                    timeout=_CALL_SHUTDOWN_CANCEL_S,
                )
            except asyncio.TimeoutError:
                _event("shutdown: TTS cleanup timed out")
            except Exception as exc:  # noqa: BLE001
                _event(f"shutdown: TTS cleanup failed: {exc}")

        if self._worker is not None:
            try:
                await asyncio.wait_for(self._worker.cancel(), timeout=_CALL_SHUTDOWN_CANCEL_S)
            except asyncio.TimeoutError:
                _event("shutdown: worker cancel timed out")
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # noqa: BLE001
                _event(f"shutdown: worker cancel failed: {exc}")

        try:
            await self._websocket.close(code=1000)
        except Exception:
            pass

        _event(f"=== CALL ENDED (reason={reason}) ===")


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
    shutdown: "_CallShutdown | None" = None
    idle_watchdog_task: asyncio.Task | None = None
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

        shutdown = _CallShutdown(
            call_control_id=call_control_id,
            websocket=websocket,
            on_begin_shutdown=None,  # set below once session_key exists
        )

        session_key = call_control_id or stream_id

        async def _mark_session_ended() -> None:
            async with _session_lock:
                _active_call_ids.discard(session_key)
                _completed_call_ids[session_key] = time.monotonic()

        shutdown._on_begin_shutdown = _mark_session_ended

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
        inbound_encoding = "PCMU"
        outbound_encoding = call_data.get("outbound_encoding") or "PCMU"
        _event(f"=== CODEC send={inbound_encoding} recv={outbound_encoding} ===")

        serializer = TelnyxFrameSerializer(
            stream_id=stream_id,
            outbound_encoding=outbound_encoding,
            inbound_encoding=inbound_encoding,
            call_control_id=call_control_id,
            api_key=settings.telnyx_api_key,
            params=TelnyxFrameSerializer.InputParams(
                auto_hang_up=False,
                sample_rate=TELEPHONY_PIPELINE_RATE,
                telnyx_sample_rate=8000,
                inbound_encoding=inbound_encoding,
                outbound_encoding=outbound_encoding,
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
            await shutdown.end_call(reason, hangup_telnyx=True)

        sample_rate = TELEPHONY_PIPELINE_RATE
        build_started = time.monotonic()
        _event(
            f"=== BUILDING PIPELINE (sample_rate={sample_rate}, "
            f"bulk_media={telephony_bulk_media_enabled()}, codec=PCMU) ==="
        )
        pipeline = build_pipeline(
            transport,
            agent_user=agent_user,
            script=script,
            mic_test=True,
            sample_rate=sample_rate,
            telephony=True,
            on_call_should_end=_on_call_should_end,
            is_call_active=lambda: not shutdown.done,
        )
        _event(
            f"=== PIPELINE BUILT in {(time.monotonic() - build_started) * 1000:.0f}ms ==="
        )
        if (time.monotonic() - build_started) > 2.0:
            _event(
                "WARNING: pipeline build >2s — Telnyx may hang up before greeting. "
                "Ensure pre-warm finished and STT reuse log appears on connect."
            )
        tts_for_cleanup = tts_processor_for_cleanup(pipeline)
        fronter = next(
            (p for p in pipeline.processors if isinstance(p, FronterProcessor)), None
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

        shutdown.attach(worker=worker, tts_for_cleanup=tts_for_cleanup)

        @transport.event_handler("on_client_connected")
        async def on_client_connected(_transport, _client) -> None:
            ms = (time.monotonic() - connect_started) * 1000
            _event(f"=== MEDIA READY — greeting should play within 1s (connect {ms:.0f}ms) ===")

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(_transport, _client) -> None:
            # Media stream died but the PSTN leg often stays open (TeXML Pause) — the
            # caller hears silence while their phone still shows connected. Always
            # REST-hangup so the line actually ends when our WebSocket closes.
            await shutdown.end_call("remote_hangup", hangup_telnyx=True)

        async def _idle_watchdog() -> None:
            """Force-end the call if nothing has happened for a while.

            Protects against a dead line where the WebSocket close frame never
            arrives (e.g. a network partition) — without this, the worker sits
            forever and the PSTN call is never released.
            """
            try:
                while True:
                    await asyncio.sleep(_IDLE_CHECK_INTERVAL_S)
                    if shutdown.done or fronter is None:
                        return
                    idle_for = time.monotonic() - fronter.last_activity_monotonic
                    if idle_for > _IDLE_TIMEOUT_S:
                        _event(f"=== IDLE TIMEOUT ({idle_for:.0f}s) — forcing hangup ===")
                        await shutdown.end_call("idle_timeout", hangup_telnyx=True)
                        return
            except asyncio.CancelledError:
                pass

        connect_started = time.monotonic()
        _event("=== STARTING RUNNER ===")
        try:
            runner = WorkerRunner(handle_sigint=False)
        except TypeError:
            runner = WorkerRunner()
        await runner.add_workers(worker)
        idle_watchdog_task = asyncio.create_task(_idle_watchdog())

        async def _run_runner() -> None:
            await runner.run()

        runner_task = asyncio.create_task(_run_runner())
        shutdown.attach(
            worker=worker,
            tts_for_cleanup=tts_for_cleanup,
            runner_task=runner_task,
        )
        try:
            await runner_task
        except asyncio.CancelledError:
            pass
        finally:
            _event("=== RUNNER FINISHED ===")
            if not shutdown.done:
                await shutdown.end_call("runner_finished", hangup_telnyx=False)
    except Exception:
        tb = traceback.format_exc()
        _event("=== CRASH ===\n" + tb)
        if shutdown is not None:
            try:
                await shutdown.end_call("exception", hangup_telnyx=True)
            except Exception as cleanup_exc:  # noqa: BLE001
                _event(f"shutdown-on-exception failed: {cleanup_exc}")
        raise
    finally:
        if idle_watchdog_task is not None:
            idle_watchdog_task.cancel()
        if session_key:
            async with _session_lock:
                _active_call_ids.discard(session_key)
                _completed_call_ids[session_key] = time.monotonic()
