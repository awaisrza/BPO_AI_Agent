"""Run the fronter pipeline in a Daily.co room (phone browser, no Twilio / no tunnel)."""

from __future__ import annotations

import os

import aiohttp
from loguru import logger

from .config import ScriptConfig, settings
from .pipeline import build_pipeline


def _prewarm_models(script: ScriptConfig) -> None:
    """Load GPU models before the caller joins (optional if pipeline lacks prewarm_voice_stack)."""
    try:
        from .pipeline import prewarm_voice_stack

        prewarm_voice_stack(script)
        return
    except ImportError:
        pass

    from .pipeline import _build_stt, _build_tts

    print("Pre-warming Whisper + Chatterbox (2-3 min on first run)…\n")
    _build_stt()
    _build_tts(script=script, sample_rate=16000)


def _require_daily() -> str:
    api_key = (settings.daily_api_key or os.getenv("DAILY_API_KEY", "")).strip()
    if not api_key:
        raise RuntimeError(
            "Daily mode needs DAILY_API_KEY in agent/.env.local\n"
            "Get one free at https://dashboard.daily.co/developers"
        )
    return api_key


async def run_daily_call(script: ScriptConfig, agent_user: str) -> None:
    """Create a Daily room, join as the bot, print link for the caller's phone."""
    from pipecat.pipeline.worker import PipelineParams, PipelineWorker
    from pipecat.runner.daily import configure
    from pipecat.transports.daily.transport import DailyParams, DailyTransport
    from pipecat.workers.runner import WorkerRunner

    api_key = _require_daily()

    print("\nPre-warming Whisper + Chatterbox (2-3 min on first run)…\n")
    _prewarm_models(script)
    print("Models ready.\n")

    async with aiohttp.ClientSession() as session:
        config = await configure(session, api_key=api_key)

    room_url = config.room_url
    print("\n=== AI FRONTER — DAILY CALL (no Twilio, no tunnel) ===")
    print(f"Open on your phone:  {room_url}")
    print("Use Chrome (Android) or Safari (iPhone). Allow mic when prompted.")
    print("Wait for the bot greeting, then talk as the lead.\n")

    sample_rate = 16000
    transport = DailyTransport(
        room_url,
        config.token,
        "Sarah",
        params=DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=sample_rate,
            audio_out_sample_rate=sample_rate,
        ),
    )

    pipeline = build_pipeline(
        transport,
        agent_user=agent_user,
        script=script,
        mic_test=True,
        sample_rate=sample_rate,
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

    @transport.event_handler("on_first_participant_joined")
    async def on_first_participant_joined(_transport, participant) -> None:
        pid = participant.get("id") if isinstance(participant, dict) else participant
        logger.info(f"Caller joined Daily room (participant={pid})")

    @transport.event_handler("on_participant_left")
    async def on_participant_left(_transport, participant, reason) -> None:
        logger.info(f"Caller left Daily room ({reason})")
        await worker.cancel()

    @transport.event_handler("on_call_state_updated")
    async def on_call_state_updated(_transport, state) -> None:
        logger.debug(f"Daily call state: {state}")

    runner = WorkerRunner()
    await runner.add_workers(worker)
    await runner.run()
