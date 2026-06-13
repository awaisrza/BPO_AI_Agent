"""Pipecat pipeline wiring: VAD -> STT -> FronterProcessor (FSM) -> TTS.

The FronterProcessor turns final transcriptions into bot replies via the conversation engine and
triggers ViciDial actions (warm transfer / disposition) when the FSM decides to.

For local testing, pass ``mic_test=True`` to skip ViciDial and use your laptop mic/speakers.
"""

from __future__ import annotations

from loguru import logger

from .config import settings, ScriptConfig
from .conversation import Action, ConversationEngine
from .fish_tts import FishAudioTTSService
from .knowledge import answer_offscript
from .vicidial import ViciDialClient

try:
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.audio.vad.vad_analyzer import VADParams
    from pipecat.frames.frames import (
        AudioRawFrame,
        EndFrame,
        InputAudioRawFrame,
        InterimTranscriptionFrame,
        StartFrame,
        SystemFrame,
        TranscriptionFrame,
        TTSSpeakFrame,
    )
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.processors.audio.vad_processor import VADProcessor
    from pipecat.processors.frame_processor import FrameProcessor
    from pipecat.services.deepgram.stt import DeepgramSTTService
    PIPECAT_AVAILABLE = True
except Exception:  # pragma: no cover - allows the FSM/tests to run without Pipecat installed
    PIPECAT_AVAILABLE = False
    FrameProcessor = object  # type: ignore


class FronterProcessor(FrameProcessor):  # type: ignore[misc]
    def __init__(
        self,
        engine: ConversationEngine,
        vicidial: ViciDialClient | None,
        agent_user: str,
        *,
        mic_test: bool = False,
    ):
        super().__init__()
        self._engine = engine
        self._vici = vicidial
        self._agent_user = agent_user
        self._mic_test = mic_test
        self._opened = False

    async def process_frame(self, frame, direction):  # type: ignore[override]
        await super().process_frame(frame, direction)

        # Mic audio must not reach TTS — only STT/VAD consume it upstream.
        if isinstance(frame, (InputAudioRawFrame, AudioRawFrame)):
            return

        if isinstance(frame, StartFrame):
            if not self._opened:
                self._opened = True
                opening = self._engine.open()
                logger.info(f"BOT: {opening.reply}")
                await self.push_frame(TTSSpeakFrame(opening.reply))
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, InterimTranscriptionFrame):
            return

        if isinstance(frame, (EndFrame, SystemFrame)):
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, TranscriptionFrame) and frame.text:
            text = frame.text.strip()
            if not text:
                return

            logger.info(f"CALLER: {text}")
            turn = self._engine.handle(text)
            logger.info(f"BOT: {turn.reply}")
            await self.push_frame(TTSSpeakFrame(turn.reply))

            if turn.action == Action.TRANSFER:
                if self._mic_test:
                    logger.info("MIC TEST -> qualified lead (warm transfer simulated)")
                else:
                    closer = self._engine.script.transfer_closer_user
                    if closer:
                        logger.info(f"FSM -> warm transfer to closer {closer}")
                        await self._vici.warm_transfer(self._agent_user, closer_user=closer)
                    else:
                        preset = (
                            self._engine.script.transfer_preset or settings.vicidial_transfer_preset
                        )
                        logger.info(f"FSM -> warm transfer (preset={preset})")
                        await self._vici.warm_transfer(self._agent_user, preset=preset)
                    await self._vici.set_disposition(self._agent_user, "XFER")
                await self.push_frame(EndFrame())
            elif turn.action == Action.HANGUP:
                if self._mic_test:
                    logger.info("MIC TEST -> call ended (hangup simulated)")
                else:
                    logger.info("FSM -> disposition + hangup")
                    await self._vici.set_disposition(self._agent_user, "NI")
                    await self._vici.hangup(self._agent_user)
                await self.push_frame(EndFrame())
            return

        await self.push_frame(frame, direction)


def _require_api_keys() -> None:
    missing = []
    if not settings.deepgram_api_key:
        missing.append("DEEPGRAM_API_KEY")
    if not settings.fish_api_key:
        missing.append("FISH_AUDIO_API_KEY")
    if not settings.google_api_key:
        missing.append("GOOGLE_API_KEY")
    if missing:
        raise RuntimeError(
            "Missing API keys for live mode: "
            + ", ".join(missing)
            + ". Add them to dashboard/.env.local or agent/.env.local."
        )


def build_pipeline(
    transport,
    *,
    agent_user: str = "MIC-TEST",
    script: ScriptConfig | None = None,
    mic_test: bool = False,
) -> Pipeline:
    """Assemble the live pipeline. `transport` provides audio in/out frames."""
    if not PIPECAT_AVAILABLE:
        raise RuntimeError(
            'Pipecat is not installed. Run: pip install "pipecat-ai[deepgram,local,silero]" pyaudio'
        )

    _require_api_keys()

    script = script or ScriptConfig.load()
    stt = DeepgramSTTService(
        api_key=settings.deepgram_api_key,
        audio_passthrough=False,
    )
    tts = FishAudioTTSService(
        api_key=settings.fish_api_key,
        model=settings.fish_model,
        reference_id=settings.fish_reference_id,
        sample_rate=16000,
    )
    vad = VADProcessor(vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.5)))

    engine = ConversationEngine(
        script=script,
        answer_offscript=lambda q, ctx: answer_offscript(q, ctx, script.knowledge_base),
    )
    vici = None if mic_test else ViciDialClient()
    fronter = FronterProcessor(engine, vici, agent_user, mic_test=mic_test)

    return Pipeline(
        [
            transport.input(),
            vad,
            stt,
            fronter,
            tts,
            transport.output(),
        ]
    )
