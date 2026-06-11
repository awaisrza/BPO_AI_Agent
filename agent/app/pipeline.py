"""Pipecat pipeline wiring: VAD -> STT -> FronterProcessor (FSM) -> TTS.

The FronterProcessor turns final transcriptions into bot replies via the conversation engine and
triggers ViciDial actions (warm transfer / disposition) when the FSM decides to.

Wire `transport` to the BPO's ViciDial media (SIP/WebRTC) during onboarding. Import paths are guarded
because Pipecat module layout shifts between releases.
"""

from __future__ import annotations

from loguru import logger

from .config import settings, ScriptConfig
from .conversation import Action, ConversationEngine
from .fish_tts import FishAudioTTSService
from .vicidial import ViciDialClient

try:
    from pipecat.frames.frames import (
        EndFrame,
        Frame,
        TranscriptionFrame,
        TTSSpeakFrame,
    )
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.task import PipelineParams, PipelineTask
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
    from pipecat.services.deepgram.stt import DeepgramSTTService
    from pipecat.services.google.llm import GoogleLLMService
    PIPECAT_AVAILABLE = True
except Exception:  # pragma: no cover - allows the FSM/tests to run without Pipecat installed
    PIPECAT_AVAILABLE = False
    FrameProcessor = object  # type: ignore
    Frame = object  # type: ignore


class FronterProcessor(FrameProcessor):  # type: ignore[misc]
    def __init__(self, engine: ConversationEngine, vicidial: ViciDialClient, agent_user: str):
        super().__init__()
        self._engine = engine
        self._vici = vicidial
        self._agent_user = agent_user
        self._opened = False

    async def process_frame(self, frame, direction):  # type: ignore[override]
        await super().process_frame(frame, direction)

        if not self._opened:
            self._opened = True
            opening = self._engine.open()
            await self.push_frame(TTSSpeakFrame(opening.reply))

        if isinstance(frame, TranscriptionFrame) and frame.text:
            turn = self._engine.handle(frame.text)
            await self.push_frame(TTSSpeakFrame(turn.reply))

            if turn.action == Action.TRANSFER:
                logger.info("FSM -> warm transfer")
                await self._vici.warm_transfer(self._agent_user)
                await self._vici.set_disposition(self._agent_user, "XFER")
                await self.push_frame(EndFrame())
            elif turn.action == Action.HANGUP:
                logger.info("FSM -> disposition + hangup")
                await self._vici.set_disposition(self._agent_user, "NI")
                await self._vici.hangup(self._agent_user)
                await self.push_frame(EndFrame())
            return

        await self.push_frame(frame, direction)


def build_pipeline(transport, *, agent_user: str, script: ScriptConfig | None = None):
    """Assemble the live pipeline. `transport` provides audio in/out frames."""
    if not PIPECAT_AVAILABLE:
        raise RuntimeError(
            "Pipecat is not installed. `pip install -r requirements.txt` to run the live pipeline."
        )

    script = script or ScriptConfig.load()
    stt = DeepgramSTTService(api_key=settings.deepgram_api_key)
    tts = FishAudioTTSService(
        api_key=settings.fish_api_key,
        model=settings.fish_model,
        reference_id=settings.fish_reference_id,
    )
    llm = GoogleLLMService(api_key=settings.google_api_key, model=settings.gemini_model)

    def answer_offscript(question: str, _ctx: str) -> str:
        # Hook the LLM for off-script questions. Kept synchronous-simple for the scaffold;
        # wire to `llm` via the OpenAI-style context aggregator for streaming in production.
        return "That's a great question — let me have a specialist cover that for you."

    engine = ConversationEngine(script=script, answer_offscript=answer_offscript)
    vici = ViciDialClient()
    fronter = FronterProcessor(engine, vici, agent_user)

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            fronter,
            llm,
            tts,
            transport.output(),
        ]
    )
    return PipelineTask(pipeline, params=PipelineParams(allow_interruptions=True))
