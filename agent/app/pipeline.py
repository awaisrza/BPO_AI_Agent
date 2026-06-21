"""Pipecat pipeline wiring: VAD -> STT -> FronterProcessor (FSM) -> TTS.

The FronterProcessor turns final transcriptions into bot replies via the conversation engine and
triggers ViciDial actions (warm transfer / disposition) when the FSM decides to.

For local testing, pass ``mic_test=True`` to skip ViciDial and use your laptop mic/speakers.

Voice backends (``VOICE_BACKEND`` env):
  - ``managed`` (default): Deepgram STT + Fish Audio TTS — pilot / no GPU
  - ``chatterbox``: faster-whisper STT + Chatterbox Turbo TTS — recommended GPU stack
  - ``gpu``: faster-whisper STT + Piper TTS — legacy / low-quality voice
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


def _script_cache_lines(script: ScriptConfig) -> list[str]:
    lines = [script.greeting, script.pitch, *script.qualifying_questions]
    lines.extend([script.transfer_line, script.not_interested_line])
    return [line.strip() for line in lines if line and line.strip()]


def _is_chatterbox_backend() -> bool:
    return settings.voice_backend == "chatterbox"


def _is_piper_backend() -> bool:
    return settings.voice_backend == "gpu"


def _is_local_gpu_backend() -> bool:
    return _is_chatterbox_backend() or _is_piper_backend()


def _require_api_keys() -> None:
    missing = []
    if not settings.google_api_key:
        missing.append("GOOGLE_API_KEY")
    if _is_local_gpu_backend():
        if _is_chatterbox_backend():
            try:
                from .chatterbox_paths import resolve_chatterbox_reference

                resolve_chatterbox_reference(settings.chatterbox_reference_audio or None)
            except FileNotFoundError as exc:
                raise RuntimeError(str(exc)) from exc
        elif _is_piper_backend():
            try:
                from .piper_paths import resolve_piper_exe, resolve_piper_model

                resolve_piper_exe(settings.piper_exe or None)
                resolve_piper_model(settings.piper_model or None)
            except FileNotFoundError as exc:
                raise RuntimeError(str(exc)) from exc
    else:
        if not settings.deepgram_api_key:
            missing.append("DEEPGRAM_API_KEY")
        if not settings.fish_api_key:
            missing.append("FISH_AUDIO_API_KEY")
    if missing:
        raise RuntimeError(
            "Missing API keys for live mode: "
            + ", ".join(missing)
            + ". Add them to dashboard/.env.local or agent/.env.local."
        )


def _build_stt():
    if _is_local_gpu_backend():
        from pipecat.services.whisper.stt import WhisperSTTService

        logger.info(
            f"STT: faster-whisper ({settings.whisper_model}, "
            f"device={settings.whisper_device}, compute={settings.whisper_compute_type})"
        )
        return WhisperSTTService(
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
            settings=WhisperSTTService.Settings(model=settings.whisper_model),
        )

    logger.info("STT: Deepgram Nova-3")
    return DeepgramSTTService(
        api_key=settings.deepgram_api_key,
        audio_passthrough=False,
    )


def _build_tts(*, script: ScriptConfig, sample_rate: int):
    if _is_chatterbox_backend():
        from .chatterbox_paths import resolve_chatterbox_device, resolve_chatterbox_reference
        from .chatterbox_tts import ChatterboxTTSService, warm_chatterbox_cache_sync

        reference = resolve_chatterbox_reference(settings.chatterbox_reference_audio or None)
        device = resolve_chatterbox_device(
            settings.chatterbox_device or settings.whisper_device or None
        )
        logger.info(f"TTS: Chatterbox Turbo (device={device}, ref={reference.name})")
        cache = warm_chatterbox_cache_sync(
            texts=_script_cache_lines(script),
            reference_path=reference,
            device=device,
            exaggeration=settings.chatterbox_exaggeration,
            cfg_weight=settings.chatterbox_cfg_weight,
            sample_rate=sample_rate,
        )
        logger.info(f"Chatterbox cache warmed: {len(cache)} script line(s)")
        return ChatterboxTTSService(
            reference_audio=str(reference),
            device=device,
            exaggeration=settings.chatterbox_exaggeration,
            cfg_weight=settings.chatterbox_cfg_weight,
            sample_rate=sample_rate,
            cache=cache,
        )

    if _is_piper_backend():
        from .piper_tts import PiperTTSService, warm_piper_cache_sync

        logger.info("TTS: Piper (local)")
        cache = warm_piper_cache_sync(
            texts=_script_cache_lines(script),
            piper_exe=settings.piper_exe or None,
            model_path=settings.piper_model or None,
            speaker=settings.piper_speaker,
            sample_rate=sample_rate,
        )
        logger.info(f"Piper cache warmed: {len(cache)} script line(s)")
        return PiperTTSService(
            piper_exe=settings.piper_exe or None,
            model_path=settings.piper_model or None,
            speaker=settings.piper_speaker,
            sample_rate=sample_rate,
            cache=cache,
        )

    logger.info("TTS: Fish Audio")
    return FishAudioTTSService(
        api_key=settings.fish_api_key,
        model=settings.fish_model,
        reference_id=settings.fish_reference_id,
        sample_rate=sample_rate,
    )


def build_pipeline(
    transport,
    *,
    agent_user: str = "MIC-TEST",
    script: ScriptConfig | None = None,
    mic_test: bool = False,
    sample_rate: int = 16000,
) -> Pipeline:
    """Assemble the live pipeline. `transport` provides audio in/out frames."""
    if not PIPECAT_AVAILABLE:
        extra = "whisper" if _is_local_gpu_backend() else "deepgram"
        raise RuntimeError(
            f'Pipecat is not installed. Run: pip install "pipecat-ai[{extra},local,silero]" pyaudio'
        )

    _require_api_keys()

    script = script or ScriptConfig.load()
    if _is_chatterbox_backend():
        backend = "Chatterbox (Whisper + Chatterbox Turbo)"
    elif _is_piper_backend():
        backend = "GPU (Whisper + Piper)"
    else:
        backend = "managed (Deepgram + Fish)"
    logger.info(f"Voice backend: {backend}")

    stt = _build_stt()
    tts = _build_tts(script=script, sample_rate=sample_rate)
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
