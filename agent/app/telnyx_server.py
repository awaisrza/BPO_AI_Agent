"""Telnyx phone-test server — real PSTN calls through the fronter pipeline.

Outbound: pass --dial on the CLI or POST /dialout.
TeXML webhook: {LOCAL_SERVER_URL}/answer
"""

from __future__ import annotations

import os
import threading
import time
import traceback
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel

from .config import ScriptConfig, settings
from .telnyx_session import run_telnyx_call

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


class DialoutBody(BaseModel):
    to_number: str
    from_number: str | None = None


def _require_telnyx() -> None:
    missing = []
    if not settings.telnyx_api_key:
        missing.append("TELNYX_API_KEY")
    if not settings.telnyx_account_sid:
        missing.append("TELNYX_ACCOUNT_SID (organization_id from whoami)")
    if not settings.telnyx_application_sid:
        missing.append("TELNYX_APPLICATION_SID (TeXML Application ID)")
    if not settings.local_server_url:
        missing.append("LOCAL_SERVER_URL (your ngrok/cloudflare https URL)")
    if missing:
        raise RuntimeError(
            "Telnyx phone mode needs these in agent/.env.local:\n  " + "\n  ".join(missing)
        )


def _websocket_url() -> str:
    base = settings.local_server_url.rstrip("/")
    ws = base.replace("https://", "wss://").replace("http://", "ws://")
    return f"{ws}/ws"


def _public_base() -> str:
    return settings.local_server_url.rstrip("/")


def _texml_for_stream() -> str:
    # Connect + Pause: Pipecat official pattern for bidirectional Telnyx audio.
    # statusCallback logs stream-started / stream-failed from Telnyx (critical for debugging).
    stream_status = f"{_public_base()}/stream-status"
    ws_url = _websocket_url()
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="{ws_url}" bidirectionalMode="rtp" bidirectionalCodec="PCMU" statusCallback="{stream_status}" statusCallbackMethod="POST"></Stream>
  </Connect>
  <Pause length="120"/>
</Response>"""


def _place_telnyx_call(*, to_number: str, from_number: str, answer_url: str) -> dict:
    url = (
        f"https://api.telnyx.com/v2/texml/Accounts/{settings.telnyx_account_sid}/Calls"
    )
    headers = {
        "Authorization": f"Bearer {settings.telnyx_api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "ApplicationSid": settings.telnyx_application_sid,
        "To": to_number,
        "From": from_number,
        "Url": answer_url,
        "StatusCallback": f"{settings.local_server_url.rstrip('/')}/status",
        "StatusCallbackMethod": "POST",
    }
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(url, headers=headers, json=payload)
        if resp.status_code != 200:
            raise RuntimeError(f"Telnyx API error ({resp.status_code}): {resp.text}")
        return resp.json()


def create_telnyx_app(script: ScriptConfig, agent_user: str) -> FastAPI:
    app = FastAPI(title="AI Fronter Telnyx Phone Test")

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"ok": True, "mode": "telnyx-phone-test"})

    @app.get("/answer")
    @app.post("/answer")
    async def answer(request: Request) -> Response:
        texml = _texml_for_stream()
        _event(f"=== /answer {request.method} -> {texml[:120]}... ===")
        return Response(content=texml, media_type="application/xml")

    @app.get("/status")
    @app.post("/status")
    async def status(request: Request) -> Response:
        # Telnyx status callbacks — always 200 so portal stops showing "failed".
        body = ""
        try:
            body = (await request.body()).decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        _event(f"=== /status {request.method} body={body!r} ===")
        return Response(content="", status_code=200)

    @app.get("/stream-status")
    @app.post("/stream-status")
    async def stream_status(request: Request) -> Response:
        # Telnyx Stream verb callbacks: stream-started, stream-stopped, stream-failed.
        body = ""
        try:
            body = (await request.body()).decode("utf-8", errors="replace")[:800]
        except Exception:
            pass
        _event(f"=== /stream-status {request.method} body={body!r} ===")
        return Response(content="", status_code=200)

    @app.post("/dialout")
    async def dialout(body: DialoutBody) -> JSONResponse:
        _require_telnyx()
        from_number = (body.from_number or settings.telnyx_phone_number or "").strip()
        if not from_number:
            raise HTTPException(
                status_code=400,
                detail="Set TELNYX_PHONE_NUMBER in .env.local or pass from_number.",
            )
        to_number = body.to_number.strip()
        if not to_number:
            raise HTTPException(status_code=400, detail="to_number is required (E.164).")

        answer_url = f"{settings.local_server_url.rstrip('/')}/answer"
        result = _place_telnyx_call(
            to_number=to_number,
            from_number=from_number,
            answer_url=answer_url,
        )
        _event(f"=== DIALOUT {to_number} ===")
        return JSONResponse({"status": "call_initiated", "to_number": to_number, "result": result})

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        _event("=== /ws INCOMING ===")
        try:
            await run_telnyx_call(websocket, script, agent_user)
        except Exception as exc:
            _event(f"=== /ws ERROR: {exc} ===\n{traceback.format_exc()}")
            try:
                await websocket.close()
            except Exception:
                pass

    return app


def _wait_for_health(port: int, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/health"
    while time.time() < deadline:
        try:
            r = httpx.get(url, timeout=1.0)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.2)
    raise RuntimeError(f"Server did not become healthy on {url}")


def run_telnyx_server(
    script: ScriptConfig,
    agent_user: str,
    *,
    dial_to: str | None = None,
) -> None:
    """Start the Telnyx phone-test server and optionally place one outbound call."""
    _require_telnyx()
    from_number = settings.telnyx_phone_number
    if dial_to and not from_number:
        raise RuntimeError("Set TELNYX_PHONE_NUMBER to use --dial.")

    # Fresh event log for this run
    try:
        _CRASH_LOG.write_text("", encoding="utf-8")
    except Exception:
        pass

    _event("Pre-warming voice stack (Chatterbox + Whisper)...")
    try:
        from .pipeline import prewarm_voice_stack

        prewarm_voice_stack(script, sample_rate=8000)
    except Exception:
        from .pipeline import _build_stt, _build_tts

        _build_stt()
        _build_tts(script=script, sample_rate=8000)
    _event("Pre-warm complete.")

    app = create_telnyx_app(script, agent_user)
    host = settings.host
    port = settings.port

    print("\n=== AI FRONTER — TELNYX PHONE TEST ===")
    print(f"Public URL:  {settings.local_server_url}")
    print(f"TeXML:       {settings.local_server_url.rstrip('/')}/answer")
    print(f"WebSocket:   {_websocket_url()}")
    print(f"Local bind:  http://{host}:{port}")
    print(f"Event log:   {_CRASH_LOG}")
    print(f"Script:      {script.greeting[:60]}...")
    print("\nPress Ctrl-C to stop.\n")

    def _dial_after_ready() -> None:
        try:
            _wait_for_health(port)
            answer_url = f"{settings.local_server_url.rstrip('/')}/answer"
            # Verify public TeXML is reachable before dialing
            try:
                pub = httpx.get(answer_url, timeout=10.0)
                _event(f"=== PUBLIC /answer status={pub.status_code} body={pub.text[:120]!r} ===")
            except Exception as exc:
                _event(f"=== PUBLIC /answer FAILED: {exc} ===")
            result = _place_telnyx_call(
                to_number=dial_to,
                from_number=from_number,
                answer_url=answer_url,
            )
            _event(f"=== DIALED {dial_to} result={result} ===")
            print(f"Dialing {dial_to} now — answer your phone.\n")
        except Exception:
            _event("=== DIAL FAILED ===\n" + traceback.format_exc())
            print("DIAL FAILED — see /tmp/telnyx_events.log")

    if dial_to:
        threading.Thread(target=_dial_after_ready, daemon=True).start()

    uvicorn.run(app, host=host, port=port, log_level="info")
