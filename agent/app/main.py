"""Entrypoint.

Default mode runs an OFFLINE TEXT SIMULATION of the conversation FSM so you can iterate on scripts
immediately without telephony or API keys. Pass `--live` to run the real Pipecat pipeline with your
laptop microphone and speakers. Pass `--browser` for WebRTC calls from a phone browser
(no Twilio/KYC). Pass `--daily` for Daily.co room link on your phone (no US number).
Pass `--phone` for real PSTN calls via Twilio, or `--telnyx` for Telnyx.

Load scripts from the dashboard (Supabase):
  python -m app.main --campaign-id <uuid>
  python -m app.main --live --bot-id <uuid>
  python -m app.main --browser --campaign-id <uuid>
  python -m app.main --daily --campaign-id <uuid>
  python -m app.main --phone --campaign-id <uuid> --dial +14155551234
  python -m app.main --telnyx --campaign-id <uuid> --dial +923001234567
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from loguru import logger

from .config import ScriptConfig
from .bot_context import BotRunContext
from .conversation import Action, ConversationEngine
from .supabase_scripts import ScriptLoadError, resolve_script
from .browser_call_server import run_browser_server
from .daily_session import run_daily_call
from .phone_server import run_phone_server
from .telnyx_server import run_telnyx_server


def _load_script_from_args(args: argparse.Namespace) -> BotRunContext:
    if args.campaign_id and args.bot_id:
        print("Use only one of --campaign-id or --bot-id.", file=sys.stderr)
        sys.exit(1)
    try:
        return resolve_script(campaign_id=args.campaign_id, bot_id=args.bot_id)
    except ScriptLoadError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)


def run_simulation(script: ScriptConfig) -> None:
    engine = ConversationEngine(script=script)
    opening = engine.open()
    print(f"\nBOT: {opening.reply}")
    print("(type the caller's replies; Ctrl-C to quit)\n")

    try:
        while True:
            caller = input("CALLER: ")
            turn = engine.handle(caller)
            print(f"BOT: {turn.reply}")
            if turn.action == Action.TRANSFER:
                print("\n>>> WARM TRANSFER to human closer. Call handed off.\n")
                break
            if turn.action == Action.HANGUP:
                print("\n>>> CALL ENDED (dispositioned).\n")
                break
    except KeyboardInterrupt:
        print("\nbye")


async def _run_live_async(ctx: BotRunContext) -> None:
    try:
        from pipecat.pipeline.worker import PipelineParams, PipelineWorker
        from pipecat.transports.local.audio import LocalAudioTransport, LocalAudioTransportParams
        from pipecat.workers.runner import WorkerRunner
    except ImportError as exc:
        raise SystemExit(
            "Live mode requires Pipecat + PyAudio.\n"
            'Run: pip install "pipecat-ai[deepgram,local,silero]" pyaudio'
        ) from exc

    from .pipeline import build_pipeline

    sample_rate = 16000
    transport = LocalAudioTransport(
        LocalAudioTransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=sample_rate,
            audio_out_sample_rate=sample_rate,
        )
    )

    pipeline = build_pipeline(
        transport,
        agent_user=ctx.agent_user,
        script=ctx.script,
        mic_test=True,
        vicidial_client=ctx.vicidial_client(),
    )
    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=sample_rate,
            audio_out_sample_rate=sample_rate,
        ),
        enable_rtvi=False,
        idle_timeout_secs=None,
    )

    print("\n=== AI FRONTER — LIVE MIC TEST ===")
    print(f"Script: {ctx.script.greeting[:50]}...")
    print(f"Qualifiers: {len(ctx.script.qualifying_questions)} question(s)")
    if ctx.vicidial_campaign_id:
        print(f"ViciDial campaign: {ctx.vicidial_campaign_id}")
    print(f"Agent user: {ctx.agent_user}")
    print("Speak into your microphone. The bot will greet you, then follow the script.")
    print("Press Ctrl-C to quit.\n")

    runner = WorkerRunner()
    await runner.add_workers(worker)
    await runner.run()


def run_live(ctx: BotRunContext) -> None:
    try:
        asyncio.run(_run_live_async(ctx))
    except KeyboardInterrupt:
        logger.info("Stopped.")


def main() -> None:
    parser = argparse.ArgumentParser(description="AI fronter agent")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run live voice test (mic -> STT -> FSM -> TTS -> speakers; backend from VOICE_BACKEND)",
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Start browser WebRTC server (phone/laptop mic — no Twilio/KYC)",
    )
    parser.add_argument(
        "--daily",
        action="store_true",
        help="Daily.co room call — open link on phone (no Twilio, no tunnel, no US number)",
    )
    parser.add_argument(
        "--phone",
        action="store_true",
        help="Start phone-test server (Twilio -> real cell/landline call)",
    )
    parser.add_argument(
        "--telnyx",
        action="store_true",
        help="Start phone-test server (Telnyx TeXML -> real cell/landline call)",
    )
    parser.add_argument(
        "--dial",
        metavar="E164",
        help="With --phone: place an outbound call to this number on startup (e.g. +14155551234)",
    )
    parser.add_argument(
        "--campaign-id",
        metavar="UUID",
        help="Load script from Supabase campaign (dashboard → Campaigns → URL id)",
    )
    parser.add_argument(
        "--bot-id",
        metavar="UUID",
        help="Load script from bot's assigned campaign (dashboard → Bots)",
    )
    args = parser.parse_args()

    ctx = _load_script_from_args(args)
    modes = sum(bool(x) for x in (args.live, args.browser, args.daily, args.phone, args.telnyx))
    if modes > 1:
        print("Use only one of --live, --browser, --daily, --phone, or --telnyx.", file=sys.stderr)
        sys.exit(1)
    if args.browser:
        run_browser_server(ctx.script, ctx.agent_user)
    elif args.daily:
        try:
            asyncio.run(run_daily_call(ctx.script, ctx.agent_user))
        except KeyboardInterrupt:
            logger.info("Stopped.")
    elif args.phone:
        run_phone_server(ctx.script, ctx.agent_user, dial_to=args.dial)
    elif args.telnyx:
        run_telnyx_server(
            ctx.script,
            ctx.agent_user,
            dial_to=args.dial,
            vicidial_client=ctx.vicidial_client(),
        )
    elif args.live:
        run_live(ctx)
    else:
        run_simulation(ctx.script)


if __name__ == "__main__":
    main()
