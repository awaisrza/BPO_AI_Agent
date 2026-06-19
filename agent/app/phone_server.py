"""Twilio phone-test server — real PSTN calls through the fronter pipeline.

Outbound: POST /dialout with your cell number, or pass --dial on the CLI.
Inbound: point your Twilio number's voice webhook at {LOCAL_SERVER_URL}/twiml
"""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse
from loguru import logger
from pydantic import BaseModel
from twilio.rest import Client as TwilioClient
from twilio.twiml.voice_response import Connect, Stream, VoiceResponse

from .config import ScriptConfig, settings
from .phone_session import run_twilio_call


class DialoutBody(BaseModel):
    to_number: str
    from_number: str | None = None


def _require_twilio() -> None:
    missing = []
    if not settings.twilio_account_sid:
        missing.append("TWILIO_ACCOUNT_SID")
    if not settings.twilio_auth_token:
        missing.append("TWILIO_AUTH_TOKEN")
    if not settings.local_server_url:
        missing.append("LOCAL_SERVER_URL (your ngrok https URL)")
    if missing:
        raise RuntimeError(
            "Phone mode needs Twilio + a public tunnel URL in dashboard/.env.local:\n  "
            + "\n  ".join(missing)
        )


def _websocket_url() -> str:
    base = settings.local_server_url.rstrip("/")
    ws = base.replace("https://", "wss://").replace("http://", "ws://")
    return f"{ws}/ws"


def _twiml_for_call(to_number: str = "", from_number: str = "") -> str:
    response = VoiceResponse()
    connect = Connect()
    stream = Stream(url=_websocket_url())
    if to_number:
        stream.parameter(name="to_number", value=to_number)
    if from_number:
        stream.parameter(name="from_number", value=from_number)
    connect.append(stream)
    response.append(connect)
    response.pause(length=30)
    return str(response)


def create_phone_app(script: ScriptConfig, agent_user: str) -> FastAPI:
    app = FastAPI(title="AI Fronter Phone Test")

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"ok": True, "mode": "phone-test"})

    @app.post("/twiml")
    async def twiml(request: Request) -> HTMLResponse:
        form = await request.form()
        content = _twiml_for_call(
            to_number=str(form.get("To") or ""),
            from_number=str(form.get("From") or ""),
        )
        return HTMLResponse(content=content, media_type="application/xml")

    @app.post("/dialout")
    async def dialout(body: DialoutBody) -> JSONResponse:
        _require_twilio()
        from_number = (body.from_number or settings.twilio_from_number or "").strip()
        if not from_number:
            raise HTTPException(
                status_code=400,
                detail="Set TWILIO_FROM_NUMBER in .env.local or pass from_number in the request.",
            )
        to_number = body.to_number.strip()
        if not to_number:
            raise HTTPException(status_code=400, detail="to_number is required (E.164, e.g. +14155551234).")

        twiml_url = f"{settings.local_server_url.rstrip('/')}/twiml"
        client = TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)
        call = client.calls.create(to=to_number, from_=from_number, url=twiml_url, method="POST")
        logger.info(f"Dialing {to_number} (call_sid={call.sid})")
        return JSONResponse({"call_sid": call.sid, "status": "call_initiated", "to_number": to_number})

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        logger.info("Twilio WebSocket accepted")
        try:
            await run_twilio_call(websocket, script, agent_user)
        except Exception as exc:
            logger.exception(f"Phone session error: {exc}")
            await websocket.close()

    return app


def run_phone_server(
    script: ScriptConfig,
    agent_user: str,
    *,
    dial_to: str | None = None,
) -> None:
    """Start the phone-test server and optionally place one outbound call."""
    _require_twilio()
    app = create_phone_app(script, agent_user)
    host = settings.host
    port = settings.port

    print("\n=== AI FRONTER — PHONE TEST (real PSTN) ===")
    print(f"Public URL:  {settings.local_server_url}")
    print(f"WebSocket:   {_websocket_url()}")
    print(f"Local bind:  http://{host}:{port}")
    print(f"Script:      {script.greeting[:60]}...")
    print("\nOutbound:  POST /dialout  {\"to_number\": \"+1...\"}")
    print("Inbound:   Twilio number voice webhook -> {LOCAL_SERVER_URL}/twiml")
    print("Press Ctrl-C to stop.\n")

    if dial_to:
        from_number = settings.twilio_from_number
        if not from_number:
            raise RuntimeError("Set TWILIO_FROM_NUMBER to use --dial.")
        twiml_url = f"{settings.local_server_url.rstrip('/')}/twiml"
        client = TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)
        call = client.calls.create(to=dial_to, from_=from_number, url=twiml_url, method="POST")
        print(f"Dialing {dial_to} now (call_sid={call.sid}) — answer your phone.\n")

    uvicorn.run(app, host=host, port=port, log_level="info")
