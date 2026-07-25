"""Telnyx phone-test server — real PSTN calls through the fronter pipeline.

Outbound: pass --dial on the CLI or POST /dialout.
TeXML webhook: {LOCAL_SERVER_URL}/answer
"""

from __future__ import annotations

import os
import socket
import threading
import time
import traceback
from pathlib import Path
from urllib.parse import parse_qs

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


def _local_server_uses_wss() -> bool:
    return _websocket_url().startswith("wss://")


def _validate_local_server_url(*, for_dial: bool = False) -> None:
    """Telnyx media requires wss://; raw Vast http://IP:port → ws:// is unstable."""
    base = settings.local_server_url.strip().rstrip("/")
    if not base:
        raise RuntimeError("Set LOCAL_SERVER_URL in agent/.env.local")
    if base.startswith("https://"):
        return
    if base.startswith("http://"):
        ws_url = _websocket_url()
        msg = (
            f"LOCAL_SERVER_URL={base!r} → WebSocket {ws_url!r}. "
            "Telnyx needs wss:// (TLS on port 443). Vast's mapped port often "
            "causes stream-error, silence, and choppy/robotic audio.\n"
            "On the GPU run: ./scripts/start-vast-tunnel.sh\n"
            "Then set LOCAL_SERVER_URL=https://....trycloudflare.com and restart."
        )
        allow = os.getenv("TELNYX_ALLOW_INSECURE_WS", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        if for_dial and not allow:
            raise RuntimeError(msg)
        _event(f"WARNING: {msg}")
        return
    raise RuntimeError(
        f"LOCAL_SERVER_URL must start with https:// (got {base!r}). "
        "Use cloudflared or ngrok on the GPU instance."
    )


def _texml_for_stream() -> str:
    stream_status = f"{_public_base()}/stream-status"
    ws_url = _websocket_url()
    codec = os.getenv("TELNYX_STREAM_CODEC", "PCMU")
    # Connect keeps the call alive until the WebSocket media path is up (Start can drop early).
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="{ws_url}" bidirectionalMode="rtp" bidirectionalCodec="{codec}" statusCallback="{stream_status}" statusCallbackMethod="POST"/>
  </Connect>
  <Pause length="120"/>
</Response>"""


def _log_greeting_cache(script: ScriptConfig) -> None:
    """Warn if the opening line is not pre-cached (Telnyx hangs up after ~3s silence)."""
    try:
        from .chatterbox_tts import TELEPHONY_PIPELINE_RATE
        from .pipeline import _cached_tts
        from .speech_renderer import render_speech_telephony

        tts = _cached_tts.get((TELEPHONY_PIPELINE_RATE, True))
        cache = getattr(tts, "_cache", None) if tts else None
        if not cache:
            _event("WARNING: TTS cache empty — first speech may take 3-5s (call may drop)")
            return
        chunks = render_speech_telephony(script.greeting)
        for idx, chunk in enumerate(chunks, start=1):
            hit = chunk.text.strip() in cache
            _event(
                f"Greeting chunk {idx} cache={'HIT' if hit else 'MISS'}: {chunk.text[:72]!r}"
            )
            if not hit:
                _event(
                    "WARNING: cache MISS on greeting — Telnyx may hang up before bot speaks. "
                    "Wait for pre-warm to finish before dialing."
                )
    except Exception as exc:
        _event(f"Greeting cache check skipped: {exc}")

    try:
        from .chatterbox_tts import TELEPHONY_PIPELINE_RATE
        from .pipeline import _cached_tts
        from .speech_renderer import render_speech_telephony, prepare_for_speech

        tts = _cached_tts.get((TELEPHONY_PIPELINE_RATE, True))
        cache = getattr(tts, "_cache", None) if tts else None
        if not cache:
            return
        kb_count = 0
        for entry in script.knowledge_base:
            spoken = prepare_for_speech(entry.answer)
            if not spoken:
                continue
            kb_count += 1
            for chunk in render_speech_telephony(spoken):
                hit = chunk.text.strip() in cache
                label = entry.topic or "KB"
                _event(
                    f"KB [{label}] cache={'HIT' if hit else 'MISS'}: {chunk.text[:64]!r}"
                )
        _event(f"Knowledge base: {kb_count} answer(s) checked in TTS cache")
    except Exception as exc:
        _event(f"KB cache check skipped: {exc}")


_TELNYX_API_RETRIES = 4
_TELNYX_API_RETRY_DELAY_S = 2.0


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
    last_exc: Exception | None = None
    retryable = (
        httpx.ConnectError,
        httpx.ReadTimeout,
        httpx.WriteTimeout,
        httpx.ReadError,
        httpx.NetworkError,
        httpx.RemoteProtocolError,
    )
    for attempt in range(1, _TELNYX_API_RETRIES + 1):
        try:
            with httpx.Client(timeout=45.0) as client:
                resp = client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(f"Telnyx API error ({resp.status_code}): {resp.text}")
            return resp.json()
        except retryable as exc:
            last_exc = exc
            _event(
                f"Telnyx API network error (attempt {attempt}/{_TELNYX_API_RETRIES}): {exc}"
            )
            if attempt < _TELNYX_API_RETRIES:
                time.sleep(_TELNYX_API_RETRY_DELAY_S * attempt)
    raise RuntimeError(
        f"Telnyx API unreachable after {_TELNYX_API_RETRIES} attempts: {last_exc}"
    ) from last_exc


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
        body = ""
        try:
            body = (await request.body()).decode("utf-8", errors="replace")
        except Exception:
            pass
        params = {k: v[0] for k, v in parse_qs(body).items()}
        summary = {
            "CallStatus": params.get("CallStatus"),
            "CallDuration": params.get("CallDuration"),
            "SipResponseCode": params.get("SipResponseCode"),
            "SipHangupCause": params.get("SipHangupCause"),
            "ErrorCode": params.get("ErrorCode") or params.get("error_code"),
            "ErrorMessage": params.get("ErrorMessage") or params.get("error_message"),
            "HangupSource": params.get("HangupSource"),
            "To": params.get("To"),
            "From": params.get("From"),
        }
        _event(f"=== /status {request.method} {summary} ===")
        hangup = params.get("SipHangupCause") or ""
        if summary.get("CallStatus") == "failed" and hangup == "404":
            _event(
                "=== CALL FAILED: SIP 404 — Telnyx could not route to this number. "
                "Enable international (Pakistan +92) on your Outbound Voice Profile, "
                "or verify the E.164 number is reachable. No WebSocket = bot never starts."
            )
        elif summary.get("CallStatus") == "completed" and params.get("HangupSource"):
            _event(f"=== CALL COMPLETE hangup_source={params.get('HangupSource')!r} ===")
        elif summary.get("CallStatus") == "failed" and not params.get("SipResponseCode"):
            _event(f"=== /status raw (truncated): {body[:500]!r} ===")
        return Response(content="", status_code=200)

    @app.get("/stream-status")
    @app.post("/stream-status")
    async def stream_status(request: Request) -> Response:
        body = ""
        try:
            body = (await request.body()).decode("utf-8", errors="replace")[:800]
        except Exception:
            pass
        _event(f"=== /stream-status {request.method} body={body!r} ===")
        if "StreamEvent=stream-error" in body or "StreamEvent=stream-failed" in body:
            ws_url = _websocket_url()
            _event(
                "=== STREAM ERROR — Telnyx could not connect to the media WebSocket. "
                f"Expected URL: {ws_url}. "
                "No /ws INCOMING log means Telnyx never reached your server. "
                "Use LOCAL_SERVER_URL=https://... (wss://) via ngrok/cloudflare — "
                "raw ws:// on a public IP often fails."
            )
        return Response(content="", status_code=200)

    @app.post("/dialout")
    async def dialout(body: DialoutBody) -> JSONResponse:
        _require_telnyx()
        _validate_local_server_url(for_dial=True)
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


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _ensure_port_free(host: str, port: int) -> None:
    probe_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    if _port_in_use(probe_host, port):
        raise RuntimeError(
            f"Port {port} is already in use — an old run_telnyx.py is still running.\n"
            f"Kill it first: kill $(lsof -t -i:{port})\n"
            "Then restart. Do not dial until you see 'Uvicorn running'."
        )


def run_telnyx_server(
    script: ScriptConfig,
    agent_user: str,
    *,
    dial_to: str | None = None,
) -> None:
    """Start the Telnyx phone-test server and optionally place one outbound call."""
    _require_telnyx()
    _validate_local_server_url(for_dial=bool(dial_to))
    from_number = settings.telnyx_phone_number
    if dial_to and not from_number:
        raise RuntimeError("Set TELNYX_PHONE_NUMBER to use --dial.")

    host = settings.host
    port = settings.port
    _ensure_port_free(host, port)

    try:
        _CRASH_LOG.write_text("", encoding="utf-8")
    except Exception:
        pass

    _event("Pre-warming voice stack (Chatterbox + Whisper)...")
    try:
        from .chatterbox_tts import TELEPHONY_PIPELINE_RATE
        from .pipeline import prewarm_voice_stack

        prewarm_voice_stack(script, sample_rate=TELEPHONY_PIPELINE_RATE, telephony=True)
        _log_greeting_cache(script)
    except Exception:
        from .chatterbox_tts import TELEPHONY_PIPELINE_RATE
        from .pipeline import _build_stt, _build_tts

        _build_stt(telephony=True)
        _build_tts(script=script, sample_rate=TELEPHONY_PIPELINE_RATE, telephony=True)
    _event("Pre-warm complete.")

    app = create_telnyx_app(script, agent_user)

    print("\n=== AI FRONTER — TELNYX PHONE TEST ===")
    print(f"Public URL:  {settings.local_server_url}")
    print(f"TeXML:       {settings.local_server_url.rstrip('/')}/answer")
    print(f"WebSocket:   {_websocket_url()}")
    ws_url = _websocket_url()
    if not _local_server_uses_wss():
        print(
            "\n*** INSECURE WEBSOCKET — expect choppy audio / stream-error ***\n"
            f"  Current: {ws_url}\n"
            "  Fix on GPU: ./scripts/start-vast-tunnel.sh\n"
            "  Then LOCAL_SERVER_URL=https://....trycloudflare.com\n"
            "  (Override only for debugging: TELNYX_ALLOW_INSECURE_WS=1)\n"
        )
        _event(f"WARNING: insecure WebSocket URL {ws_url} — Telnyx may send stream-error")
    else:
        _event(f"WebSocket URL OK: {ws_url}")
    print(f"Local bind:  http://{host}:{port}")
    print(f"Event log:   {_CRASH_LOG}")
    print(f"Script:      {script.greeting[:60]}...")
    print("\nPress Ctrl-C to stop.\n")

    def _dial_after_ready() -> None:
        try:
            try:
                _validate_local_server_url(for_dial=True)
            except RuntimeError as exc:
                _event(f"=== DIAL BLOCKED: {exc} ===")
                print(f"\n*** DIAL BLOCKED ***\n{exc}\n")
                return
            _wait_for_health(port)
            answer_url = f"{settings.local_server_url.rstrip('/')}/answer"
            local_answer = f"http://127.0.0.1:{port}/answer"
            try:
                local = httpx.get(local_answer, timeout=3.0)
                _event(f"=== LOCAL /answer status={local.status_code} ===")
            except Exception as exc:
                _event(f"=== LOCAL /answer FAILED: {exc} ===")
                print("Server not responding locally — aborting dial.")
                return
            try:
                pub = httpx.get(answer_url, timeout=20.0)
                _event(f"=== PUBLIC /answer status={pub.status_code} body={pub.text[:120]!r} ===")
                ws_url = _websocket_url()
                if "Connect" not in pub.text and "Stream" not in pub.text:
                    _event("WARNING: /answer TeXML missing Connect/Stream")
                _event(f"=== EXPECT WS URL: {ws_url} ===")
            except Exception as exc:
                _event(f"=== PUBLIC /answer FAILED: {exc} ===")
                print(
                    "\n*** NGROK TUNNEL NOT REACHABLE ***\n"
                    "Restart ngrok, copy the new https URL into agent/.env.local "
                    "(LOCAL_SERVER_URL=...), then restart run_telnyx.py.\n"
                    "Dial aborted to avoid a silent call with no media.\n"
                )
                return
            # Brief Telnyx API reachability check before placing the call.
            for probe in range(1, 4):
                try:
                    httpx.head("https://api.telnyx.com", timeout=10.0)
                    break
                except Exception as exc:
                    _event(f"Telnyx API probe failed ({probe}/3): {exc}")
                    if probe == 3:
                        print(
                            "\n*** TELNYX API UNREACHABLE ***\n"
                            "The GPU cannot reach https://api.telnyx.com right now.\n"
                            "Check Telnyx status, firewall, or retry in 30–60 seconds.\n"
                            "  curl -I https://api.telnyx.com\n"
                        )
                        return
                    time.sleep(3.0 * probe)
            result = _place_telnyx_call(
                to_number=dial_to,
                from_number=from_number,
                answer_url=answer_url,
            )
            _event(f"=== DIALED {dial_to} result={result} ===")
            print(f"Dialing {dial_to} now — answer your phone.")
            print("Keep this server running until the call ends (do not Ctrl+C early).\n")
        except Exception:
            _event("=== DIAL FAILED ===\n" + traceback.format_exc())
            print("DIAL FAILED — see /tmp/telnyx_events.log")
            print(
                "If the error mentions SSL/EOF, retry in a few seconds or run:\n"
                "  curl -I https://api.telnyx.com\n"
            )

    if dial_to:
        threading.Thread(target=_dial_after_ready, daemon=True).start()

    # Keep the Telnyx media WebSocket alive through proxies / idle gaps.
    ws_ping = float(os.getenv("TELNYX_WS_PING_INTERVAL", "20") or "20")
    ws_timeout = float(os.getenv("TELNYX_WS_PING_TIMEOUT", "20") or "20")
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        ws_ping_interval=ws_ping,
        ws_ping_timeout=ws_timeout,
    )
