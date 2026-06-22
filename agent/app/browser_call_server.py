"""Browser WebRTC call server — real two-way voice without Twilio/KYC.

Open the URL on your phone (Chrome/Safari), allow the microphone, and talk to the
bot running Chatterbox + benu on the GPU host. Use ngrok/cloudflare tunnel when
the server is on Vast and your phone is elsewhere.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from loguru import logger

from .browser_session import run_browser_call
from .config import ScriptConfig, settings

_FALLBACK_CLIENT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AI Fronter — Browser Call</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 32rem; margin: 2rem auto; padding: 0 1rem; }
    button { font-size: 1.1rem; padding: 0.75rem 1.25rem; margin-right: 0.5rem; }
    #status { margin: 1rem 0; color: #444; }
    audio { width: 100%; margin-top: 1rem; }
  </style>
</head>
<body>
  <h1>AI Fronter</h1>
  <p>Two-way voice test — Chatterbox on GPU. Allow microphone when prompted.</p>
  <button id="connect">Start call</button>
  <button id="hangup" disabled>End call</button>
  <div id="status">Idle</div>
  <audio id="remote" autoplay playsinline></audio>
  <script>
    let pc = null;
    let pcId = null;
    let localStream = null;
    const statusEl = document.getElementById("status");
    const remoteEl = document.getElementById("remote");
    const connectBtn = document.getElementById("connect");
    const hangupBtn = document.getElementById("hangup");

    function setStatus(msg) { statusEl.textContent = msg; }

    async function sendCandidate(candidate) {
      if (!pcId || !candidate) return;
      await fetch("/api/offer", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          pc_id: pcId,
          candidates: [{
            candidate: candidate.candidate,
            sdp_mid: candidate.sdpMid,
            sdp_mline_index: candidate.sdpMLineIndex
          }]
        })
      });
    }

    async function startCall() {
      connectBtn.disabled = true;
      setStatus("Requesting microphone…");
      pc = new RTCPeerConnection({
        iceServers: [{ urls: "stun:stun.l.google.com:19302" }]
      });
      localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      localStream.getTracks().forEach((track) => pc.addTrack(track, localStream));

      pc.ontrack = (event) => {
        remoteEl.srcObject = event.streams[0];
      };
      pc.onicecandidate = (event) => {
        sendCandidate(event.candidate).catch((err) => console.error(err));
      };
      pc.onconnectionstatechange = () => {
        setStatus("Connection: " + pc.connectionState);
        if (pc.connectionState === "connected") hangupBtn.disabled = false;
        if (pc.connectionState === "failed" || pc.connectionState === "closed") {
          hangupBtn.disabled = true;
          connectBtn.disabled = false;
        }
      };

      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      setStatus("Connecting to bot…");

      const resp = await fetch("/api/offer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sdp: offer.sdp, type: offer.type })
      });
      if (!resp.ok) {
        const detail = await resp.text();
        throw new Error(detail || resp.statusText);
      }
      const answer = await resp.json();
      pcId = answer.pc_id;
      await pc.setRemoteDescription(answer);
      setStatus("Connected — speak when the bot greets you.");
    }

    function endCall() {
      if (localStream) localStream.getTracks().forEach((t) => t.stop());
      if (pc) pc.close();
      pc = null;
      pcId = null;
      localStream = null;
      remoteEl.srcObject = null;
      connectBtn.disabled = false;
      hangupBtn.disabled = true;
      setStatus("Call ended.");
    }

    connectBtn.onclick = () => startCall().catch((err) => {
      console.error(err);
      setStatus("Error: " + err.message);
      endCall();
    });
    hangupBtn.onclick = endCall;
  </script>
</body>
</html>
"""


def _public_base_url(host: str, port: int) -> str:
    if settings.local_server_url.strip():
        return settings.local_server_url.rstrip("/")
    if host in ("0.0.0.0", "::"):
        return f"http://127.0.0.1:{port}"
    return f"http://{host}:{port}"


def create_browser_app(script: ScriptConfig, agent_user: str) -> FastAPI:
    from pipecat.transports.smallwebrtc.request_handler import (
        IceCandidate,
        SmallWebRTCPatchRequest,
        SmallWebRTCRequest,
        SmallWebRTCRequestHandler,
    )

    webrtc_handler = SmallWebRTCRequestHandler()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        await webrtc_handler.close()

    app = FastAPI(title="AI Fronter Browser Call", lifespan=lifespan)

    try:
        from pipecat_ai_prebuilt.frontend import PipecatPrebuiltUI

        app.mount("/client", PipecatPrebuiltUI)

        @app.get("/", include_in_schema=False)
        async def root_redirect() -> RedirectResponse:
            return RedirectResponse(url="/client/")

        ui_mode = "Pipecat prebuilt UI at /client/"
    except ImportError:
        @app.get("/", include_in_schema=False)
        async def fallback_client() -> HTMLResponse:
            return HTMLResponse(_FALLBACK_CLIENT_HTML)

        ui_mode = "built-in call page at /"

    app.state.ui_mode = ui_mode

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"ok": True, "mode": "browser-webrtc"})

    @app.post("/api/offer")
    async def offer(
        request: Request,
        background_tasks: BackgroundTasks,
    ) -> JSONResponse:
        body = await request.json()
        webrtc_request = SmallWebRTCRequest.from_dict(body)

        async def on_connection(connection) -> None:
            background_tasks.add_task(run_browser_call, connection, script, agent_user)

        answer = await webrtc_handler.handle_web_request(
            request=webrtc_request,
            webrtc_connection_callback=on_connection,
        )
        if answer is None:
            raise HTTPException(status_code=500, detail="WebRTC negotiation failed")
        return JSONResponse(answer)

    @app.patch("/api/offer")
    async def ice_candidate(request: Request) -> JSONResponse:
        body = await request.json()
        patch = SmallWebRTCPatchRequest(
            pc_id=body["pc_id"],
            candidates=[IceCandidate(**c) for c in body.get("candidates", [])],
        )
        await webrtc_handler.handle_patch_request(patch)
        return JSONResponse({"status": "success"})

    return app


def run_browser_server(script: ScriptConfig, agent_user: str) -> None:
    """Start WebRTC server for phone/laptop browser calls (no Twilio)."""
    app = create_browser_app(script, agent_user)
    host = settings.host
    port = settings.port
    public = _public_base_url(host, port)

    print("\n=== AI FRONTER — BROWSER CALL (WebRTC, no Twilio) ===")
    print(f"Open in browser:  {public}/")
    print(f"Local bind:       http://{host}:{port}")
    print(f"Script:           {script.greeting[:60]}...")
    print(f"UI:               {getattr(app.state, 'ui_mode', 'built-in call page at /')}")
    if not settings.local_server_url.strip():
        print(
            "\nPhone on another network? Expose this port with ngrok/cloudflare, set "
            "LOCAL_SERVER_URL in .env.local, restart, then open that URL on your phone."
        )
    else:
        print(f"\nOn your phone: open {public}/ in Chrome or Safari and allow the mic.")
    print("Press Ctrl-C to stop.\n")

    uvicorn.run(app, host=host, port=port, log_level="info")
