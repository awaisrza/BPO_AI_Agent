"""Run the fronter pipeline on a Twilio Media Streams WebSocket (real PSTN call)."""

from __future__ import annotations

from loguru import logger

from .config import ScriptConfig, settings
from .pipeline import build_pipeline


async def run_twilio_call(websocket, script: ScriptConfig, agent_user: str) -> None:
    """Handle one inbound or outbound Twilio call over Media Streams."""
    from pipecat.pipeline.worker import PipelineParams, PipelineWorker
    from pipecat.runner.utils import parse_telephony_websocket
    from pipecat.serializers.twilio import TwilioFrameSerializer
    from pipecat.transports.websocket.fastapi import (
        FastAPIWebsocketParams,
        FastAPIWebsocketTransport,
    )
    from pipecat.workers.runner import WorkerRunner

    transport_type, call_data = await parse_telephony_websocket(websocket)
    body = call_data.get("body") or {}
    logger.info(
        f"Phone call connected ({transport_type}) "
        f"to={body.get('to_number', '?')} from={body.get('from_number', '?')}"
    )

    serializer = TwilioFrameSerializer(
        stream_sid=call_data["stream_id"],
        call_sid=call_data["call_id"],
        account_sid=settings.twilio_account_sid,
        auth_token=settings.twilio_auth_token,
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

    sample_rate = 8000
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

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(_transport, _client) -> None:
        logger.info("Phone call ended")
        await worker.cancel()

    runner = WorkerRunner()
    await runner.add_workers(worker)
    await runner.run()
