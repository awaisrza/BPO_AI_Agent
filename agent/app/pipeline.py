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
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Awaitable, Callable

from loguru import logger

from .config import settings, ScriptConfig
from .conversation import (
    Action,
    ConversationEngine,
    Intent,
    _looks_like_question,
)

# Dedicated pool for FSM turns that may call Gemini. Do NOT use the default
# asyncio executor here — Chatterbox TTS also parks CUDA synth on that pool,
# and a queued/stuck synth job can starve greeting/consent turns for 10s+
# (caller hears silence after "I am good." until they hang up).
_FSM_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="fsm")
from .fish_tts import FishAudioTTSService
from .gemini import FALLBACK_REPLY, TELEPHONY_KB_MISS_REPLY
from .knowledge import answer_offscript
from .speech_renderer import (
    BargeInProcessor,
    CallController,
    CallState,
    RtpKeepaliveStartFrame,
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
        VADUserStartedSpeakingFrame,
        VADUserStoppedSpeakingFrame,
    )
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.processors.audio.vad_processor import VADProcessor
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
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
    "click",
    "clicks",
    "tick",
    ".",
    "..",
    "...",
})


_STT_GREETING_FIXES = {
    "i'm dead": "I'm good",
    "im dead": "I'm good",
    "i am dead": "I am good",
}


def _normalize_caller_stt(text: str) -> str:
    key = text.strip().lower().rstrip(".")
    return _STT_GREETING_FIXES.get(key, text)


def _is_meaningful_caller_text(text: str) -> bool:
    t = text.strip().lower().rstrip(".")
    if len(t) < 2:
        return False
    if t in _STT_IGNORE:
        return False
    words = [w for w in t.replace(",", " ").split() if w]
    if len(words) == 1 and len(words[0]) <= 2 and words[0] not in {"no", "yes"}:
        return False
    return True


def should_telephony_barge_in(text: str, engine: ConversationEngine) -> bool:
    """Stop bot playback on PSTN when the caller asks a real question (KB or off-script)."""
    normalized = _normalize_caller_stt(text)
    if not _is_meaningful_caller_text(normalized):
        return False
    if _looks_like_question(normalized):
        return True
    return bool(engine._kb_only_answer(normalized))


class FronterProcessor(FrameProcessor):  # type: ignore[misc]
    def __init__(
        self,
        engine: ConversationEngine,
        vicidial: ViciDialClient | None,
        agent_user: str,
        *,
        mic_test: bool = False,
        call_controller: CallController | None = None,
        telephony: bool = False,
        telephony_phone_test: bool = False,
        on_call_should_end: "Callable[[str], Awaitable[None]] | None" = None,
        is_call_active: "Callable[[], bool] | None" = None,
    ):
        super().__init__()
        self._engine = engine
        self._vici = vicidial
        self._agent_user = agent_user
        self._mic_test = mic_test
        self._telephony = telephony
        self._telephony_phone_test = telephony_phone_test
        self._on_call_should_end = on_call_should_end
        self._is_call_active = is_call_active
        self._pending_terminal_action: str | None = None
        self._opened = False
        self._call = call_controller or CallController()
        self._pending_caller_texts: list[str] = []
        self._followup_reply: str | None = None
        self._caller_buffer: str = ""
        self._flush_task: asyncio.Task | None = None
        self._caller_flush_delay_s = 0.4 if (telephony or telephony_phone_test) else 0.75
        self.last_activity_monotonic: float = time.monotonic()

    def _touch_activity(self) -> None:
        self.last_activity_monotonic = time.monotonic()

    def _call_live(self) -> bool:
        return self._is_call_active is None or self._is_call_active()

    async def _start_telephony_keepalive(self) -> None:
        if not self._telephony or not PIPECAT_AVAILABLE:
            return
        # Must route through the pipeline so keepalive runs inside TTS process_frame
        # (calling tts.push_frame from here does not reach Telnyx in PipelineWorker).
        await self.push_frame(RtpKeepaliveStartFrame(), FrameDirection.DOWNSTREAM)

    async def _interrupt_and_handle_caller(self, text: str, direction) -> None:  # type: ignore[no-untyped-def]
        """Stop current TTS and answer the caller immediately (telephony KB/questions)."""
        logger.info(f"Telephony barge-in — answering caller: {text[:64]!r}")
        self._cancel_flush_task()
        self._followup_reply = None
        self._call.on_interruption()
        await self.push_frame(InterruptionFrame(), direction)
        await asyncio.sleep(0.05)
        self._call.finish_bot_playback()
        await self._start_telephony_keepalive()
        await self._handle_caller(_normalize_caller_stt(text))

    def _maybe_barge_in_for_caller(self, text: str) -> bool:
        return self._telephony and should_telephony_barge_in(text, self._engine)

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
        # Keep both — never drop an earlier answer for a longer clarification.
        return f"{prev_s} {new_s}"

    def _buffer_caller_text(self, text: str) -> None:
        if not text.strip():
            return
        self._caller_buffer = self._merge_transcripts(self._caller_buffer, text)

    def _has_pending_caller(self) -> bool:
        return bool(self._pending_caller_texts) or bool(self._caller_buffer.strip())

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
        cleaned = text.strip()
        if not cleaned:
            return
        # Queue each distinct utterance — do not overwrite earlier answers.
        if self._pending_caller_texts:
            last = self._pending_caller_texts[-1].lower()
            if cleaned.lower() in last or last in cleaned.lower():
                if len(cleaned) > len(self._pending_caller_texts[-1]):
                    self._pending_caller_texts[-1] = cleaned
                logger.info(
                    "STT heard caller while bot speaking — queued: "
                    f"{self._pending_caller_texts[-1][:64]!r}"
                )
                return
        self._pending_caller_texts.append(cleaned)
        logger.info(
            "STT heard caller while bot speaking — queued: "
            f"{cleaned[:64]!r} ({len(self._pending_caller_texts)} waiting)"
        )

    def _collapse_caller_queue(self) -> str | None:
        """Combine everything the caller said while the bot was busy.

        Previously this picked a single "winner" utterance by priority (question >
        short yes/no > consent phrase) and silently discarded the rest. If VAD split
        one continuous answer into two utterances across a natural pause (e.g. "Yes
        I am" + "I turned 66 last year"), the second half — often the actually
        informative part — was thrown away entirely. Now every queued utterance is
        merged (same dedup logic as the live buffer), so nothing the caller said is
        ever dropped.
        """
        if not self._pending_caller_texts:
            return None
        items = list(self._pending_caller_texts)
        self._pending_caller_texts.clear()
        merged = ""
        for item in items:
            merged = self._merge_transcripts(merged, item)
        if len(items) > 1:
            logger.info(
                f"STT queue merged {len(items)} utterances -> {merged[:80]!r}"
            )
        return _normalize_caller_stt(merged) if merged else None

    def _move_pending_to_buffer(self) -> None:
        if not self._pending_caller_texts:
            return
        next_text = self._collapse_caller_queue()
        if not next_text:
            return
        self._caller_buffer = next_text

    def _engine_may_block(self, text: str) -> bool:
        """True when handle() might invoke answer_offscript (Gemini / slow I/O)."""
        if self._engine.answer_offscript is None:
            return False
        # Local KB hit is sync and cheap — no need to leave the event loop.
        if self._engine._kb_only_answer(text):
            return False
        intent = self._engine.classify(text, self._engine.state.value)
        return intent in (Intent.QUESTION, Intent.NEGATIVE)

    async def _run_engine(self, text: str):
        """Run the FSM without starving keepalive; only park a worker for Gemini."""
        t0 = time.perf_counter()
        if self._engine_may_block(text):
            loop = asyncio.get_running_loop()
            turn = await loop.run_in_executor(_FSM_EXECUTOR, self._engine.handle, text)
        else:
            # Greeting acks / consent / yes-no qualify — must stay on the loop so a
            # busy default executor (Chatterbox) cannot delay the next BOT line.
            turn = self._engine.handle(text)
        ms = (time.perf_counter() - t0) * 1000
        if ms >= 50:
            logger.info(f"FSM handled in {ms:.0f}ms")
        else:
            logger.debug(f"FSM handled in {ms:.0f}ms")
        return turn

    async def _handle_caller(self, text: str) -> None:
        if not self._call_live():
            return
        text = _normalize_caller_stt(text)
        self._call.close_user_turn()
        self._call.on_processing()
        await self._start_telephony_keepalive()
        logger.info(f"CALLER: {text}")
        self._touch_activity()
        turn = await self._run_engine(text)
        spoken = render_speech(turn.reply)
        logger.info(f"BOT: {' | '.join(c.text for c in spoken) or turn.reply}")
        followup = self._engine.take_pending_followup()
        self._followup_reply = followup or None
        if followup:
            logger.info(f"BOT follow-up queued: {followup[:64]!r}")
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
            if self._telephony:
                # Defer termination until the closing line's BotStoppedSpeakingFrame
                # arrives — EndFrame is a SystemFrame and can jump the queue ahead of
                # still-playing audio, cutting the closer line off mid-sentence.
                self._pending_terminal_action = "transfer"
            elif not self._telephony_phone_test:
                await self.push_frame(EndFrame())
        elif turn.action == Action.HANGUP:
            if self._mic_test:
                logger.info("MIC TEST -> call ended (hangup simulated)")
            else:
                logger.info("FSM -> disposition + hangup")
                await self._vici.set_disposition(self._agent_user, "NI")
                await self._vici.hangup(self._agent_user)
            if self._telephony:
                self._pending_terminal_action = "hangup"
            elif not self._telephony_phone_test:
                await self.push_frame(EndFrame())

    async def process_frame(self, frame, direction):  # type: ignore[override]
        if not self._call_live() and not isinstance(frame, (StartFrame, SystemFrame)):
            return
        await super().process_frame(frame, direction)

        # Mic audio must not reach TTS — only STT/VAD consume it upstream.
        if isinstance(frame, (InputAudioRawFrame, AudioRawFrame)):
            return

        if isinstance(frame, StartFrame):
            if not self._opened:
                self._opened = True
                self._touch_activity()
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
            # FSM decided to hang up / transfer — the closing line has now fully
            # played, so it's safe to actually end the call. This takes priority
            # over any queued caller speech or follow-up (the conversation is over).
            if self._pending_terminal_action:
                action = self._pending_terminal_action
                self._pending_terminal_action = None
                if not self._call.can_accept_caller():
                    self._call.finish_bot_playback()
                if self._on_call_should_end is not None:
                    await self._on_call_should_end(action)
                await self.push_frame(frame, direction)
                return
            # Caller speech waiting always beats a scripted follow-up re-ask.
            if self._pending_caller_texts:
                if self._followup_reply:
                    logger.info(
                        "Dropping bot follow-up — caller has queued speech waiting"
                    )
                    self._followup_reply = None
                if not self._call.can_accept_caller():
                    self._call.finish_bot_playback()
                await self._start_telephony_keepalive()
                logger.info("Bot playback done — releasing queued caller audio")
                self._move_pending_to_buffer()
                if self._caller_buffer:
                    self._schedule_caller_flush()
                await self.push_frame(frame, direction)
                return
            if self._followup_reply:
                followup = self._followup_reply
                self._followup_reply = None
                spoken = render_speech(followup)
                logger.info(
                    f"BOT follow-up: {' | '.join(c.text for c in spoken) or followup}"
                )
                if self._telephony:
                    pause_s = settings.telephony_followup_pause_s
                    if pause_s > 0:
                        logger.info(
                            f"Telephony follow-up pause ({pause_s:.1f}s) before follow-up line"
                        )
                        await self._start_telephony_keepalive()
                        await asyncio.sleep(pause_s)
                self._call.on_processing()
                await self.push_frame(TTSSpeakFrame(followup))
                await self.push_frame(frame, direction)
                return
            if not self._call.can_accept_caller():
                self._call.finish_bot_playback()
            if self._call.can_accept_caller():
                # Telnyx drops the media stream after ~3s with no outbound RTP.
                # Keepalive must run for the whole listen window — not only when
                # caller text is already queued (after greeting that gap killed calls).
                if self._telephony:
                    await self._start_telephony_keepalive()
                    logger.info("Telephony listen — waiting for caller")
                self._move_pending_to_buffer()
                if self._caller_buffer:
                    self._schedule_caller_flush()
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, VADUserStartedSpeakingFrame):
            if self._telephony and self._call.can_accept_caller():
                self._touch_activity()
                await self._start_telephony_keepalive()
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, VADUserStoppedSpeakingFrame):
            if self._pending_caller_texts and self._call.can_accept_caller():
                self._move_pending_to_buffer()
            if self._call.can_accept_caller() and self._caller_buffer:
                await self._flush_caller_buffer()
            elif self._caller_buffer:
                self._schedule_caller_flush()
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, (EndFrame, SystemFrame)):
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, TranscriptionFrame) and frame.text:
            text = frame.text.strip()
            if not text:
                return
            self._touch_activity()

            if not self._call.can_accept_caller():
                if self._call.state in (CallState.SPEAKING, CallState.PROCESSING):
                    if self._maybe_barge_in_for_caller(text):
                        await self._interrupt_and_handle_caller(text, direction)
                        return
                    self._queue_pending_caller_text(text)
                elif self._pending_caller_texts:
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
    if telephony:
        # Must match SpeechRendererNode (telephony_utterance_max_words), not speech_max_words.
        max_words = settings.telephony_utterance_max_words
    engine = ConversationEngine(script=script)
    lines = [
        script.greeting,
        script.pitch,
        engine._consent_prompt(),
        engine._short_prompt,
        *script.qualifying_questions,
    ]
    lines.extend([script.transfer_line, script.not_interested_line])
    consent_q = engine._pitch_consent_question()
    for entry in script.knowledge_base:
        answer = prepare_for_speech(entry.answer)
        if not answer:
            continue
        lines.append(answer)
        if telephony:
            lines.append(f"{answer} {consent_q}")
            lines.append(f"{answer} {engine._short_prompt}")
            for question in script.qualifying_questions:
                lines.append(f"{answer} {question}")
    if telephony:
        lines.append(TELEPHONY_KB_MISS_REPLY)
        lines.append(FALLBACK_REPLY)
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
        stop_secs=settings.telephony_vad_stop_secs,
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
            telephony=telephony,
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
    on_call_should_end: "Callable[[str], Awaitable[None]] | None" = None,
    is_call_active: "Callable[[], bool] | None" = None,
) -> Pipeline:
    """Assemble the live pipeline. `transport` provides audio in/out frames."""
    global _cached_stt

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

    # Telephony: reuse pre-warmed Whisper when available (fresh load costs ~7s silence).
    if telephony:
        if _cached_stt is not None:
            stt = _cached_stt
            logger.info("STT: reusing pre-warmed Whisper for telephony")
        else:
            stt = _build_stt(telephony=True)
            _cached_stt = stt
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
        telephony=telephony,
        telephony_phone_test=telephony and mic_test,
        on_call_should_end=on_call_should_end,
        is_call_active=is_call_active,
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

    processors = [
        transport.input(),
        vad,
        barge_in,
        stt,
        fronter,
        speech_renderer,
        tts,
    ]
    if telephony:
        from .telnyx_media import TelnyxBulkMediaProcessor, telephony_bulk_media_enabled

        if telephony_bulk_media_enabled():
            ws_client = getattr(transport, "_client", None)
            if ws_client is not None:

                async def _send_json(payload: str) -> None:
                    await ws_client.send(payload)

                encoding = os.getenv("TELNYX_STREAM_CODEC", "PCMU")
                processors.append(
                    TelnyxBulkMediaProcessor(send_json=_send_json, encoding=encoding)
                )
                logger.info(f"Telnyx bulk media enabled (encoding={encoding})")
            else:
                logger.warning("Telnyx bulk media skipped — transport has no WebSocket client")
    processors.append(transport.output())

    return Pipeline(processors)
