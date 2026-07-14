"""Pipecat pipeline wiring: VAD -> STT -> FronterProcessor -> SpeechRenderer -> TTS.

The FronterProcessor turns final transcriptions into bot replies via the conversation engine and
triggers ViciDial actions (warm transfer / disposition) when the FSM decides to.

All bot speech passes through SpeechRendererNode (short spoken chunks + pauses) before TTS.
BargeInProcessor stops TTS when the caller speaks over the bot.

For local testing, pass ``mic_test=True`` to skip ViciDial and use your laptop mic/speakers.

Voice backends (``VOICE_BACKEND`` env):
  - ``managed`` (default): Deepgram STT + Fish Audio TTS — pilot / no GPU
  - ``chatterbox``: faster-whisper STT + Chatterbox Turbo TTS — recommended GPU stack
  - ``gpu``: faster-whisper STT + Piper TTS — legacy / low-quality voice
"""

from __future__ import annotations

import asyncio

from loguru import logger

from .config import settings, ScriptConfig
from .conversation import Action, ConversationEngine
from .fish_tts import FishAudioTTSService
from .gemini import TELEPHONY_KB_MISS_REPLY
from .knowledge import answer_offscript
from .speech_renderer import (
    BargeInProcessor,
    CallController,
    CallState,
    SpeechRendererNode,
    iter_chunk_texts,
    prepare_for_speech,
    render_speech,
)
from .vicidial import ViciDialClient

try:
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.audio.vad.vad_analyzer import VADParams
    from pipecat.frames.frames import (
        AudioRawFrame,
        BotStoppedSpeakingFrame,
        EndFrame,
        InputAudioRawFrame,
        InterimTranscriptionFrame,
        InterruptionFrame,
        StartFrame,
        SystemFrame,
        TranscriptionFrame,
        TTSSpeakFrame,
        VADUserStoppedSpeakingFrame,
    )
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.processors.audio.vad_processor import VADProcessor
    from pipecat.processors.frame_processor import FrameProcessor
    from pipecat.services.deepgram.stt import DeepgramSTTService
    PIPECAT_AVAILABLE = True
except Exception:  # pragma: no cover - allows the FSM/tests to run without Pipecat installed
    PIPECAT_AVAILABLE = False
    FrameProcessor = object  # type: ignore


_STT_IGNORE = frozenset({
    "you",
    "the",
    "a",
    "an",
    "oh",
    "um",
    "uh",
    "hmm",
    "bye",
    "thanks",
    "thank you",
    ".",
    "..",
    "...",
})


def _is_meaningful_caller_text(text: str) -> bool:
    t = text.strip().lower()
    if len(t) < 2:
        return False
    if t in _STT_IGNORE:
        return False
    words = [w for w in t.replace(",", " ").split() if w]
    if len(words) == 1 and len(words[0]) <= 2 and words[0] not in {"no", "yes"}:
        return False
    return True


class FronterProcessor(FrameProcessor):  # type: ignore[misc]
    def __init__(
        self,
        engine: ConversationEngine,
        vicidial: ViciDialClient | None,
        agent_user: str,
        *,
        mic_test: bool = False,
        call_controller: CallController | None = None,
        telephony_phone_test: bool = False,
    ):
        super().__init__()
        self._engine = engine
        self._vici = vicidial
        self._agent_user = agent_user
        self._mic_test = mic_test
        self._telephony_phone_test = telephony_phone_test
        self._opened = False
        self._call = call_controller or CallController()
        self._pending_caller_text: str | None = None
        self._caller_buffer: str = ""
        self._flush_task: asyncio.Task | None = None
        self._caller_flush_delay_s = 0.75

    def _merge_transcripts(self, prev: str, new: str) -> str:
        prev_s, new_s = prev.strip(), new.strip()
        if not prev_s:
            return new_s
        if not new_s:
            return prev_s
        pl, nl = prev_s.lower(), new_s.lower()
        if nl in pl:
            return prev_s
        if pl in nl:
            return new_s
        return new_s if len(new_s) >= len(prev_s) else prev_s

    def _buffer_caller_text(self, text: str) -> None:
        if not text.strip():
            return
        self._caller_buffer = self._merge_transcripts(self._caller_buffer, text)

    def _cancel_flush_task(self) -> None:
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
        self._flush_task = None

    def _schedule_caller_flush(self) -> None:
        if not PIPECAT_AVAILABLE:
            return
        self._cancel_flush_task()

        async def _delayed_flush() -> None:
            try:
                await asyncio.sleep(self._caller_flush_delay_s)
                await self._flush_caller_buffer()
            except asyncio.CancelledError:
                pass

        self._flush_task = asyncio.create_task(_delayed_flush())

    async def _flush_caller_buffer(self) -> None:
        self._cancel_flush_task()
        if not self._call.can_accept_caller():
            return
        text = self._caller_buffer.strip()
        self._caller_buffer = ""
        if not _is_meaningful_caller_text(text):
            logger.info(f"Ignoring low-confidence STT fragment: {text!r}")
            return
        self._call.close_user_turn()
        await self._handle_caller(text)

    def _queue_pending_caller_text(self, text: str) -> None:
        if not _is_meaningful_caller_text(text):
            return
        prev = self._pending_caller_text
        self._pending_caller_text = self._merge_transcripts(prev, text) if prev else text
        logger.info(
            "STT heard caller while bot speaking — queued: "
            f"{self._pending_caller_text[:64]!r}"
        )

    def _move_pending_to_buffer(self) -> None:
        if not self._pending_caller_text:
            return
        self._buffer_caller_text(self._pending_caller_text)
        self._pending_caller_text = None

    async def _handle_caller(self, text: str) -> None:
        self._call.close_user_turn()
        self._call.on_processing()
        logger.info(f"CALLER: {text}")
        turn = self._engine.handle(text)
        spoken = render_speech(turn.reply)
        logger.info(f"BOT: {' | '.join(c.text for c in spoken) or turn.reply}")
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
            if not self._telephony_phone_test:
                await self.push_frame(EndFrame())
        elif turn.action == Action.HANGUP:
            if self._mic_test:
                logger.info("MIC TEST -> call ended (hangup simulated)")
            else:
                logger.info("FSM -> disposition + hangup")
                await self._vici.set_disposition(self._agent_user, "NI")
                await self._vici.hangup(self._agent_user)
            await self.push_frame(EndFrame())

    async def process_frame(self, frame, direction):  # type: ignore[override]
        await super().process_frame(frame, direction)

        # Mic audio must not reach TTS — only STT/VAD consume it upstream.
        if isinstance(frame, (InputAudioRawFrame, AudioRawFrame)):
            return

        if isinstance(frame, StartFrame):
            if not self._opened:
                self._opened = True
                self._call.state = CallState.LISTENING
                opening = self._engine.open()
                spoken = render_speech(opening.reply)
                logger.info(f"BOT: {' | '.join(c.text for c in spoken) or opening.reply}")
                await self.push_frame(TTSSpeakFrame(opening.reply))
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, InterruptionFrame):
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, InterimTranscriptionFrame):
            return

        if isinstance(frame, BotStoppedSpeakingFrame):
            if self._pending_caller_text and not self._call.can_accept_caller():
                self._call.finish_bot_playback()
                logger.info("Bot playback done — releasing queued caller audio")
            if self._call.can_accept_caller():
                self._move_pending_to_buffer()
                if self._caller_buffer:
                    self._schedule_caller_flush()
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, VADUserStoppedSpeakingFrame):
            if self._call.can_accept_caller() and self._caller_buffer:
                await self._flush_caller_buffer()
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, (EndFrame, SystemFrame)):
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, TranscriptionFrame) and frame.text:
            text = frame.text.strip()
            if not text:
                return

            if not self._call.can_accept_caller():
                if self._call.state in (CallState.SPEAKING, CallState.PROCESSING):
                    self._queue_pending_caller_text(text)
                elif self._pending_caller_text:
                    self._queue_pending_caller_text(text)
                return

            if not _is_meaningful_caller_text(text):
                return

            self._buffer_caller_text(text)
            logger.info(f"STT buffered caller text: {text[:64]!r}")
            self._schedule_caller_flush()
            return

        await self.push_frame(frame, direction)


def _speech_settings(*, telephony: bool = False) -> tuple[int, int, int]:
    if telephony:
        return (
            settings.telephony_speech_max_words,
            settings.telephony_pause_min_ms,
            settings.telephony_pause_max_ms,
        )
    return (
        settings.speech_max_words,
        settings.speech_pause_min_ms,
        settings.speech_pause_max_ms,
    )


def _script_cache_lines(script: ScriptConfig, *, telephony: bool = False) -> list[str]:
    max_words, pause_min, pause_max = _speech_settings(telephony=telephony)
    lines = [script.greeting, script.pitch, *script.qualifying_questions]
    lines.extend([script.transfer_line, script.not_interested_line])
    for entry in script.knowledge_base:
        answer = prepare_for_speech(entry.answer)
        if answer:
            lines.append(answer)
    if telephony:
        lines.append(TELEPHONY_KB_MISS_REPLY)
    raw = [line.strip() for line in lines if line and line.strip()]
    return iter_chunk_texts(
        raw,
        telephony=telephony,
        max_words=max_words,
        pause_min_ms=pause_min,
        pause_max_ms=pause_max,
    )


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


def _telephony_vad_params() -> VADParams:
    """PSTN audio is quieter and noisier than a laptop mic — relax Silero thresholds."""
    return VADParams(
        confidence=0.55,
        start_secs=0.2,
        stop_secs=0.9,
        min_volume=0.35,
    )


def _build_vad(*, telephony: bool = False) -> VADProcessor:
    params = _telephony_vad_params() if telephony else VADParams(stop_secs=0.5)
    return VADProcessor(
        vad_analyzer=SileroVADAnalyzer(params=params),
        audio_idle_timeout=2.0 if telephony else 1.0,
    )


def _build_stt(*, telephony: bool = False):
    if _is_local_gpu_backend():
        from pipecat.services.whisper.stt import WhisperSTTService
        from pipecat.transcriptions.language import Language

        no_speech_prob = 0.65 if telephony else 0.4
        logger.info(
            f"STT: faster-whisper ({settings.whisper_model}, "
            f"device={settings.whisper_device}, compute={settings.whisper_compute_type}, "
            f"telephony={telephony}, no_speech_prob={no_speech_prob})"
        )
        return WhisperSTTService(
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
            settings=WhisperSTTService.Settings(
                model=settings.whisper_model,
                language=Language.EN,
                no_speech_prob=no_speech_prob,
            ),
        )

    logger.info("STT: Deepgram Nova-3")
    return DeepgramSTTService(
        api_key=settings.deepgram_api_key,
        audio_passthrough=False,
    )


def _build_tts(*, script: ScriptConfig, sample_rate: int, telephony: bool = False):
    if _is_chatterbox_backend():
        from .chatterbox_paths import resolve_chatterbox_device, resolve_chatterbox_reference
        from .chatterbox_tts import ChatterboxTTSService, TELEPHONY_PIPELINE_RATE, warm_chatterbox_cache_sync

        reference = resolve_chatterbox_reference(settings.chatterbox_reference_audio or None)
        device = resolve_chatterbox_device(
            settings.chatterbox_device or settings.whisper_device or None
        )
        telephony = telephony or sample_rate == TELEPHONY_PIPELINE_RATE
        logger.info(
            f"TTS: Chatterbox Turbo (device={device}, ref={reference.name}, telephony={telephony})"
        )
        try:
            cache = warm_chatterbox_cache_sync(
                texts=_script_cache_lines(script, telephony=telephony),
                reference_path=reference,
                device=device,
                exaggeration=settings.chatterbox_exaggeration,
                cfg_weight=settings.chatterbox_cfg_weight,
                sample_rate=sample_rate,
                telephony=telephony,
            )
        except Exception as exc:
            logger.warning(f"Chatterbox cache warm failed (live synthesis only): {exc}")
            cache = {}
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
            texts=_script_cache_lines(script, telephony=telephony),
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


_cached_stt = None
_cached_tts: dict[tuple[int, bool], object] = {}


def prewarm_voice_stack(
    script: ScriptConfig | None = None,
    *,
    sample_rate: int = 16000,
    telephony: bool = False,
) -> None:
    """Load STT/TTS weights before the first live call (avoids blocking on connect)."""
    global _cached_stt, _cached_tts
    _require_api_keys()
    script = script or ScriptConfig.load()
    from .chatterbox_tts import TELEPHONY_PIPELINE_RATE

    if sample_rate == TELEPHONY_PIPELINE_RATE:
        telephony = True
    logger.info(
        f"Pre-warming voice stack (sample_rate={sample_rate}, telephony={telephony})..."
    )
    _cached_stt = _build_stt(telephony=telephony)
    _cached_tts[(sample_rate, telephony)] = _build_tts(
        script=script, sample_rate=sample_rate, telephony=telephony
    )
    logger.info("Voice stack pre-warm complete.")


def build_pipeline(
    transport,
    *,
    agent_user: str = "MIC-TEST",
    script: ScriptConfig | None = None,
    mic_test: bool = False,
    sample_rate: int = 16000,
    telephony: bool = False,
) -> Pipeline:
    """Assemble the live pipeline. `transport` provides audio in/out frames."""
    if not PIPECAT_AVAILABLE:
        extra = "whisper" if _is_local_gpu_backend() else "deepgram"
        raise RuntimeError(
            f'Pipecat is not installed. Run: pip install "pipecat-ai[{extra},local,silero]" pyaudio'
        )

    _require_api_keys()

    from .chatterbox_tts import TELEPHONY_PIPELINE_RATE

    if sample_rate == TELEPHONY_PIPELINE_RATE:
        telephony = True

    script = script or ScriptConfig.load()
    if _is_chatterbox_backend():
        backend = "Chatterbox (Whisper + Chatterbox Turbo)"
    elif _is_piper_backend():
        backend = "GPU (Whisper + Piper)"
    else:
        backend = "managed (Deepgram + Fish)"
    mode = "telephony" if telephony else "local"
    logger.info(f"Voice backend: {backend} ({mode}, {sample_rate} Hz)")

    # Telephony: fresh STT per call — shared WhisperSTTService blocks StartFrame on reconnect.
    if telephony:
        stt = _build_stt(telephony=True)
    else:
        stt = _cached_stt or _build_stt(telephony=False)
    tts_base = _cached_tts.get((sample_rate, telephony)) or _build_tts(
        script=script, sample_rate=sample_rate, telephony=telephony
    )
    # Each call gets its own TTS instance (shared warm cache) so GPU locks from a
    # prior call cannot block StartFrame on a Telnyx reconnect.
    if telephony and hasattr(tts_base, "clone_with_shared_cache"):
        tts = tts_base.clone_with_shared_cache()
    else:
        tts = tts_base
    vad = _build_vad(telephony=telephony)

    engine = ConversationEngine(
        script=script,
        answer_offscript=lambda q, ctx: answer_offscript(
            q, ctx, script.knowledge_base, telephony=telephony
        ),
    )
    call_controller = CallController()
    vici = None if mic_test else ViciDialClient()
    fronter = FronterProcessor(
        engine,
        vici,
        agent_user,
        mic_test=mic_test,
        call_controller=call_controller,
        telephony_phone_test=telephony and mic_test,
    )
    barge_in = BargeInProcessor(call_controller, telephony=telephony)
    max_words, pause_min, pause_max = _speech_settings(telephony=telephony)
    speech_renderer = SpeechRendererNode(
        call_controller,
        max_words=max_words,
        pause_min_ms=pause_min,
        pause_max_ms=pause_max,
        telephony=telephony and settings.telephony_single_utterance,
        telephony_max_words=settings.telephony_utterance_max_words,
    )

    return Pipeline(
        [
            transport.input(),
            vad,
            barge_in,
            stt,
            fronter,
            speech_renderer,
            tts,
            transport.output(),
        ]
    )
