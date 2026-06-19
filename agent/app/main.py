"""Entrypoint.

Default mode runs an OFFLINE TEXT SIMULATION of the conversation FSM so you can iterate on scripts
immediately without telephony or API keys. Pass `--live` to run the real Pipecat pipeline with your
laptop microphone and speakers. Pass `--phone` for real PSTN calls via Twilio.

Load scripts from the dashboard (Supabase):
  python -m app.main --campaign-id <uuid>
  python -m app.main --live --bot-id <uuid>
  python -m app.main --phone --campaign-id <uuid> --dial +14155551234
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from loguru import logger

from .config import ScriptConfig
from .conversation import Action, ConversationEngine
from .supabase_scripts import ScriptLoadError, resolve_script
from .phone_server import run_phone_server


def _load_script_from_args(args: argparse.Namespace) -> tuple[ScriptConfig, str]:
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


async def _run_live_async(script: ScriptConfig, agent_user: str) -> None:
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
        agent_user=agent_user,
        script=script,
        mic_test=True,
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
    print(f"Script: {script.greeting[:50]}...")
    print(f"Qualifiers: {len(script.qualifying_questions)} question(s)")
    print("Speak into your microphone. The bot will greet you, then follow the script.")
    print("Press Ctrl-C to quit.\n")

    runner = WorkerRunner()
    await runner.add_workers(worker)
    await runner.run()


def run_live(script: ScriptConfig, agent_user: str) -> None:
    try:
        asyncio.run(_run_live_async(script, agent_user))
    except KeyboardInterrupt:
        logger.info("Stopped.")


def main() -> None:
    parser = argparse.ArgumentParser(description="AI fronter agent")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run live voice test (mic -> Deepgram -> FSM -> Fish -> speakers)",
    )
    parser.add_argument(
        "--phone",
        action="store_true",
        help="Start phone-test server (Twilio -> real cell/landline call)",
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

    script, agent_user = _load_script_from_args(args)
    if args.phone:
        if args.live:
            print("Use --phone or --live, not both.", file=sys.stderr)
            sys.exit(1)
        run_phone_server(script, agent_user, dial_to=args.dial)
    elif args.live:
        run_live(script, agent_user)
    else:
        run_simulation(script)


if __name__ == "__main__":
    main()
