"""Manual test client for SIP edge → GPU worker bridge (no FreeSWITCH required)."""

from __future__ import annotations

import argparse
import asyncio
import base64
import json

from app.sip_telephony import bootstrap_silence_messages, build_connected, build_start, media_message, new_stream_id, ulaw_silence_chunk


async def _run(args: argparse.Namespace) -> None:
    import websockets

    params = f"agent_user={args.agent}&org_id={args.org_id}"
    url = f"{args.sip_edge.rstrip('/')}/v1/stream?{params}"
    print(f"Connecting to SIP edge {url}")

    async with websockets.connect(url) as ws:
        # SIP edge accepts and bridges; send PCMU like FreeSWITCH mod_audio_stream would.
        silence = base64.b64encode(ulaw_silence_chunk()).decode("ascii")
        for _ in range(30):
            await ws.send(media_message(silence))
            await asyncio.sleep(0.02)
        print("Sent bootstrap silence; waiting for bot audio (Ctrl-C to stop)...")
        try:
            async for message in ws:
                data = json.loads(message)
                if data.get("event") == "media":
                    print(".", end="", flush=True)
        except KeyboardInterrupt:
            print("\nDone.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Test SIP edge WebSocket bridge")
    parser.add_argument("--agent", required=True, help="ViciDial agent user")
    parser.add_argument("--org-id", required=True, help="Organization UUID")
    parser.add_argument("--sip-edge", default="ws://127.0.0.1:8790", help="SIP edge base URL")
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
