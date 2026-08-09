"""Patch vicidial_session.py for fast second-call handoff."""
from __future__ import annotations

import re
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "app" / "vicidial_session.py"
text = p.read_text(encoding="utf-8")

old_accept = '''async def _ensure_websocket_accepted(websocket) -> None:
    """Accept only if Uvicorn/Starlette has not already accepted the socket."""
    try:
        from starlette.websockets import WebSocketState

        if websocket.application_state == WebSocketState.CONNECTING:
            await websocket.accept()
    except RuntimeError as exc:
        # Newer uvicorn accepts before the handler runs — second accept crashes.
        if "websocket.accept" not in str(exc):
            raise
'''

new_accept = '''async def _ensure_websocket_accepted(websocket) -> None:
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
'''

if old_accept not in text:
    raise SystemExit("accept block not found")
text = text.replace(old_accept, new_accept, 1)

old_const = "_CALL_SHUTDOWN_CANCEL_S = 5.0\n\n\nclass _CallShutdown:"
new_const = """_CALL_SHUTDOWN_CANCEL_S = 2.0
_RUNNER_JOIN_TIMEOUT_S = 3.0


def _is_client_disconnected(exc: BaseException) -> bool:
    name = type(exc).__name__
    if name == "ClientDisconnected":
        return True
    mod = type(exc).__module__ or ""
    return "ClientDisconnected" in name or "ClientDisconnected" in str(exc) or (
        "uvicorn" in mod and "disconnect" in name.lower()
    )


class _CallShutdown:"""
if old_const not in text:
    raise SystemExit("const block not found")
text = text.replace(old_const, new_const, 1)

old_init = (
    "        self._runner_task: asyncio.Task | None = None\n"
    "        self._done = False\n\n"
    "    def attach"
)
new_init = (
    "        self._runner_task: asyncio.Task | None = None\n"
    "        self._done = False\n"
    "        self._cleanup_task: asyncio.Task | None = None\n\n"
    "    def attach"
)
if old_init not in text:
    raise SystemExit("init block not found")
text = text.replace(old_init, new_init, 1)

pattern = re.compile(
    r"    async def end_call\(self, reason: str\) -> None:.*?"
    r'                _event\(f"shutdown: worker cancel failed: \{exc\}"\)\n',
    re.S,
)
match = pattern.search(text)
if not match:
    raise SystemExit("end_call block not found")

new_end_call = '''    async def end_call(self, reason: str) -> None:
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
'''
text = text[: match.start()] + new_end_call + text[match.end() :]

old_try = '''    try:
        await _ensure_websocket_accepted(websocket)
        try:
            transport_type, call_data = await parse_telephony_websocket(websocket)'''
new_try = '''    try:
        try:
            await _ensure_websocket_accepted(websocket)
        except Exception as exc:  # noqa: BLE001
            if _is_client_disconnected(exc):
                _event("=== VICIDIAL WS client disconnected before accept ===")
                return
            raise
        try:
            transport_type, call_data = await parse_telephony_websocket(websocket)'''
if old_try not in text:
    raise SystemExit("try accept block not found")
text = text.replace(old_try, new_try, 1)

old_runner = '''        try:
            await runner_task
        except asyncio.CancelledError:
            pass
        finally:
            _event("=== pipeline worker finished ===")
            if not shutdown.done:
                end_reason = "runner_finished"
                await shutdown.end_call("runner_finished")
    except Exception:
        _event("=== VICIDIAL CRASH ===\\n" + traceback.format_exc())
        if shutdown is not None:
            end_reason = "exception"
            await shutdown.end_call("exception")
        raise
'''
new_runner = '''        try:
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
        _event("=== VICIDIAL CRASH ===\\n" + traceback.format_exc())
        if shutdown is not None:
            end_reason = "exception"
            await shutdown.end_call("exception")
        raise
'''
if old_runner not in text:
    raise SystemExit("runner block not found")
text = text.replace(old_runner, new_runner, 1)

p.write_bytes(text.encode("utf-8"))
print("patched", p)
