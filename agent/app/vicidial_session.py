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
from .config import settings
from .pipeline import FronterProcessor, build_pipeline, tts_processor_for_cleanup
from .telnyx_media import (
    TelnyxBulkMediaProcessor,
    greeting_pcm_from_cache,
    send_direct_bulk_pcm,
    telephony_bulk_media_enabled,
)

_CRASH_LOG = Path("/tmp/vicidial_events.log")
_active_sessions: set[str] = set()
_session_lock = asyncio.Lock()
_call_runner_lock = asyncio.Lock()
_IDLE_TIMEOUT_S = 120.0
_IDLE_CHECK_INTERVAL_S = 10.0
_GREETING_KICK_DELAY_S = 2.0


def _greeting_startup_timeout_s() -> float:
    return settings.telephony_greeting_startup_timeout_s


def call_runner_ready() -> bool:
    """True when the worker can accept a new ViciDial media WebSocket."""
    return not _call_runner_lock.locked()


async def _ensure_websocket_accepted(websocket) -> None:
    """Accept only if Uvicorn/Starlette has not already accepted the socket."""
    try:
        from starlette.websockets import WebSocketState

        if websocket.application_state == WebSocketState.CONNECTING:
            await websocket.accept()
    except RuntimeError as exc:
        # Newer uvicorn accepts before the handler runs — second accept crashes.
        if "websocket.accept" not in str(exc):
            raise
    except Exception as exc:  # noqa: BLE001
        if _is_client_disconnected(exc):
            raise
        raise


def _looks_like_vicidial_call_id(value: str) -> bool:
    token = (value or "").strip()
    if len(token) < 12:
        return False
    return token[0] in ("V", "Y") and token[1:].replace("-", "").isalnum()


def _extract_vicidial_call_id(cd: dict[str, Any]) -> str | None:
    """Remote-agent call ID from bridge Telnyx start (ra_call_control value)."""
    for key in ("vicidial_call_id",):
        raw = cd.get(key)
        if raw and _looks_like_vicidial_call_id(str(raw)):
            return str(raw).strip()
    body = cd.get("body")
    if isinstance(body, dict):
        raw = body.get("vicidial_call_id")
        if raw and _looks_like_vicidial_call_id(str(raw)):
            return str(raw).strip()
        start = body.get("start")
        if isinstance(start, dict):
            raw = start.get("vicidial_call_id")
            if raw and _looks_like_vicidial_call_id(str(raw)):
                return str(raw).strip()
    return None


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


_CALL_SHUTDOWN_CANCEL_S = 2.0
_RUNNER_JOIN_TIMEOUT_S = 3.0


def _is_client_disconnected(exc: BaseException) -> bool:
    name = type(exc).__name__
    if name == "ClientDisconnected":
        return True
    mod = type(exc).__module__ or ""
    return "ClientDisconnected" in name or "ClientDisconnected" in str(exc) or (
        "uvicorn" in mod and "disconnect" in name.lower()
    )


class _CallShutdown:
    def __init__(self, *, session_key: str, websocket) -> None:
        self._session_key = session_key
        self._websocket = websocket
        self._worker = None
        self._tts_for_cleanup = None
        self._runner_task: asyncio.Task | None = None
        self._done = False
        self._cleanup_task: asyncio.Task | None = None

    def attach(self, *, worker, tts_for_cleanup, runner_task: asyncio.Task | None = None) -> None:
        self._worker = worker
        self._tts_for_cleanup = tts_for_cleanup
        self._runner_task = runner_task

    @property
    def done(self) -> bool:
        return self._done

    async def end_call(self, reason: str) -> None:
        if self._done:
            return
        self._done = True
        _event(f"=== VICIDIAL END CALL (reason={reason}) ===")

        # Close bridge WS first so ViciDial can hear disconnect while we tear down GPU work.
        try:
            await self._websocket.close(code=1000)
        except Exception:
            pass

        if self._runner_task is not None and not self._runner_task.done():
            self._runner_task.cancel()

        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(
                self._cleanup_pipeline(reason),
                name=f"vicidial-cleanup-{self._session_key[:12]}",
            )

    async def _cleanup_pipeline(self, reason: str) -> None:
        """Best-effort teardown — must not block the next call's call_runner_lock."""
        if self._tts_for_cleanup is not None and hasattr(
            self._tts_for_cleanup, "cancel_background_work"
        ):
            try:
                await asyncio.wait_for(
                    self._tts_for_cleanup.cancel_background_work(),
                    timeout=_CALL_SHUTDOWN_CANCEL_S,
                )
            except asyncio.TimeoutError:
                _event("shutdown: TTS cleanup timed out — continuing in background")
            except Exception as exc:  # noqa: BLE001
                _event(f"shutdown: TTS cleanup failed: {exc}")

        if self._worker is not None:
            try:
                await asyncio.wait_for(self._worker.cancel(), timeout=_CALL_SHUTDOWN_CANCEL_S)
            except asyncio.TimeoutError:
                _event(
                    "shutdown: worker cancel timed out — releasing call slot "
                    f"(reason={reason})"
                )
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # noqa: BLE001
                _event(f"shutdown: worker cancel failed: {exc}")

        if self._runner_task is not None and not self._runner_task.done():
            self._runner_task.cancel()
            try:
                await asyncio.wait_for(self._runner_task, timeout=_CALL_SHUTDOWN_CANCEL_S)
            except (asyncio.TimeoutError, asyncio.CancelledError):
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
    greeting_watchdog_task: asyncio.Task | None = None
    greeting_kick_task: asyncio.Task | None = None
    active_call = None
    end_reason: str | None = None
    fronter = None

    try:
        try:
            await _ensure_websocket_accepted(websocket)
        except Exception as exc:  # noqa: BLE001
            if _is_client_disconnected(exc):
                _event("=== VICIDIAL WS client disconnected before accept ===")
                return
            raise
        try:
            transport_type, call_data = await parse_telephony_websocket(websocket)
        except ValueError as exc:
            if "WebSocket closed before receiving telephony handshake" in str(exc):
                _event("=== VICIDIAL WS closed before handshake (bridge retry/probe) ===")
                await websocket.close(code=1000)
                return
            raise
        cd = _call_data_dict(call_data)
        vicidial_call_id = _extract_vicidial_call_id(cd)
        if vicidial_call_id:
            _event(f"=== ViciDial remote call id={vicidial_call_id} ===")
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

        from .call_lifecycle import begin_call

        phone = (cd.get("call_id") or cd.get("from") or cd.get("caller") or "").strip() or None
        active_call = begin_call(
            ctx,
            session_id=session_key,
            phone=phone,
            vicidial_call_id=vicidial_call_id,
        )

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
            nonlocal end_reason
            end_reason = reason
            await shutdown.end_call(reason)

        vici = ctx.vicidial_client()
        build_started = time.monotonic()
        _event(
            f"=== BUILDING PIPELINE (bulk_media={telephony_bulk_media_enabled()}) ==="
        )
        pipeline = build_pipeline(
            transport,
            agent_user=ctx.agent_user,
            script=ctx.script,
            mic_test=False,
            sample_rate=TELEPHONY_PIPELINE_RATE,
            telephony=True,
            vicidial_client=vici,
            vicidial_call_id=vicidial_call_id,
            on_call_should_end=_on_call_should_end,
            is_call_active=lambda: not shutdown.done,
        )
        build_ms = (time.monotonic() - build_started) * 1000
        _event(f"=== PIPELINE BUILT in {build_ms:.0f}ms ===")
        if build_ms > 2000:
            _event(
                "WARNING: pipeline build >2s — greeting may miss bridge sync window. "
                "Ensure fleet_worker pre-warm finished before dialing."
            )

        tts_for_cleanup = tts_processor_for_cleanup(pipeline)
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

        media_ready_at: float | None = None

        async def _greeting_startup_watchdog() -> None:
            """Release a stuck call slot if Chatterbox never produces greeting audio."""
            timeout_s = _greeting_startup_timeout_s()
            try:
                await asyncio.sleep(timeout_s)
                if shutdown.done or fronter is None or media_ready_at is None:
                    return
                # StartFrame can run before on_client_connected; _opened means greeting queued.
                if fronter._opened:
                    return
                if fronter.last_activity_monotonic <= media_ready_at:
                    _event(
                        f"=== GREETING STARTUP TIMEOUT ({timeout_s:.0f}s) — "
                        "no bot activity after media ready ==="
                    )
                    await shutdown.end_call("greeting_startup_timeout")
            except asyncio.CancelledError:
                pass

        bulk_media = next(
            (p for p in pipeline.processors if isinstance(p, TelnyxBulkMediaProcessor)),
            None,
        )
        bulk_encoding = (
            bulk_media._encoding if bulk_media is not None else os.getenv("TELNYX_STREAM_CODEC", "PCMU")
        )

        async def _ws_send_json(payload: str) -> None:
            await websocket.send_text(payload)

        async def _kick_greeting_if_stuck() -> None:
            """If StartFrame is slow, play cached greeting PCM directly on the media WS."""
            try:
                await asyncio.sleep(_GREETING_KICK_DELAY_S)
                if shutdown.done or fronter is None or fronter._opened:
                    return

                from .speech_renderer import CallState

                _event(
                    f"=== StartFrame delayed >{_GREETING_KICK_DELAY_S:.0f}s — kicking greeting ==="
                )
                opening = fronter._engine.open()
                fronter._opened = True
                fronter._touch_activity()
                fronter._call.state = CallState.LISTENING

                tts_src = tts_for_cleanup or next(
                    (p for p in pipeline.processors if getattr(p, "_cache", None)),
                    None,
                )
                pcm = None
                if tts_src is not None:
                    pcm = greeting_pcm_from_cache(
                        tts_src,
                        opening.reply,
                        script_greeting=ctx.script.greeting,
                        telephony_max_words=settings.telephony_utterance_max_words,
                        greeting_single_chunk=settings.telephony_greeting_single_chunk,
                    )
                if pcm:
                    duration_ms = await send_direct_bulk_pcm(
                        _ws_send_json,
                        pcm,
                        sample_rate=TELEPHONY_PIPELINE_RATE,
                        encoding=bulk_encoding,
                    )
                    _event(f"=== greeting kick sent direct bulk media (~{duration_ms}ms) ===")
                    return

                _event("=== greeting kick failed: no cached greeting PCM ===")
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # noqa: BLE001
                _event(f"=== greeting kick failed: {exc} ===")

        @transport.event_handler("on_client_connected")
        async def on_client_connected(_transport, _client) -> None:
            nonlocal media_ready_at
            media_ready_at = time.monotonic()
            if fronter is not None and fronter._opened:
                fronter._touch_activity()
            _event("=== MEDIA READY — greeting should play within 1s ===")
            nonlocal greeting_kick_task
            greeting_kick_task = asyncio.create_task(_kick_greeting_if_stuck())

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(_transport, _client) -> None:
            await shutdown.end_call("remote_hangup")

        connect_started = time.monotonic()
        runner = WorkerRunner(handle_sigint=False)
        await runner.add_workers(worker)
        idle_watchdog_task = asyncio.create_task(_idle_watchdog())
        greeting_watchdog_task = asyncio.create_task(_greeting_startup_watchdog())
        _event("=== pipeline worker running ===")

        async def _run_runner() -> None:
            await runner.run()

        runner_task = asyncio.create_task(_run_runner())
        shutdown.attach(worker=worker, tts_for_cleanup=tts_for_cleanup, runner_task=runner_task)
        try:
            await asyncio.wait_for(runner_task, timeout=_RUNNER_JOIN_TIMEOUT_S)
        except asyncio.TimeoutError:
            _event(
                f"=== runner join timed out after {_RUNNER_JOIN_TIMEOUT_S:.0f}s "
                "— releasing call slot for next dial ==="
            )
            if shutdown is not None and not shutdown.done:
                await shutdown.end_call("runner_join_timeout")
        except asyncio.CancelledError:
            pass
        finally:
            _event("=== pipeline worker finished ===")
            if shutdown is not None and not shutdown.done:
                end_reason = "runner_finished"
                await shutdown.end_call("runner_finished")
    except Exception as exc:
        if _is_client_disconnected(exc):
            _event("=== VICIDIAL WS client gone (bridge closed early) ===")
            if shutdown is not None and not shutdown.done:
                end_reason = "client_disconnected"
                await shutdown.end_call("client_disconnected")
            return
        _event("=== VICIDIAL CRASH ===\n" + traceback.format_exc())
        if shutdown is not None:
            end_reason = "exception"
            await shutdown.end_call("exception")
        raise
    finally:
        if idle_watchdog_task is not None:
            idle_watchdog_task.cancel()
        if greeting_watchdog_task is not None:
            greeting_watchdog_task.cancel()
        if greeting_kick_task is not None:
            greeting_kick_task.cancel()
        if session_key:
            async with _session_lock:
                _active_sessions.discard(session_key)
        if active_call is not None:
            from .call_lifecycle import complete_call

            transferred = False
            if fronter is not None:
                from .conversation import State

                transferred = fronter._engine.state == State.TRANSFER
            await asyncio.to_thread(
                complete_call,
                ctx,
                active_call,
                reason=end_reason or "runner_finished",
                transferred=transferred,
            )
        if ctx.bot_id:
            from .fleet_worker import patch_bot_status

            await asyncio.to_thread(patch_bot_status, ctx.bot_id, "idle")
