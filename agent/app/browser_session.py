"""Run the fronter pipeline on a browser WebRTC connection (no Twilio / no KYC)."""

from __future__ import annotations

from loguru import logger

from .config import ScriptConfig
from .pipeline import build_pipeline


async def run_browser_call(connection, script: ScriptConfig, agent_user: str) -> None:
    """Handle one browser WebRTC session (phone or laptop mic in Chrome/Safari)."""
    from pipecat.pipeline.worker import PipelineParams, PipelineWorker
    from pipecat.transports.base_transport import TransportParams
    from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
    from pipecat.workers.runner import WorkerRunner

    logger.info(f"Browser call connected (pc_id={connection.pc_id})")

    sample_rate = 16000
    transport = SmallWebRTCTransport(
        webrtc_connection=connection,
        params=TransportParams(
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

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(_transport, _client) -> None:
        logger.info("Browser call ended")
        await worker.cancel()

    runner = WorkerRunner()
    await runner.add_workers(worker)
    await runner.run()
